const {
    execSync
} = require('child_process');
const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');
const ChromeProfileManager = require('./chrome-profile-manager');

const args = process.argv.slice(2);
let profileName = 'profile1';
let questionsFile = 'inputs/gemini.yml';
let axWatch = null;
let axFiles = false;
let axRoles = null;
let axMethod = 'playwright';
let waitBetweenQuestions = 3000;
let waitForResponse = 30000;
let headless = false;
let topic = 'latest AI agent automation development for past 1 week';

for (let i = 0; i < args.length; i++) {
    if (args[i].startsWith('--')) {
        const flag = args[i];
        if (flag === '--questions' || flag === '-q') {
            questionsFile = args[++i];
        } else if (flag === '--ax-watch') {
            axWatch = parseInt(args[++i]) || 5000;
        } else if (flag === '--ax-files') {
            axFiles = true;
        } else if (flag === '--ax-roles') {
            axRoles = args[++i].split(',').map(r => r.trim());
        } else if (flag === '--ax-cdp') {
            axMethod = 'cdp';
        } else if (flag === '--wait-between') {
            waitBetweenQuestions = parseInt(args[++i]) || 3000;
        } else if (flag === '--wait-response') {
            waitForResponse = parseInt(args[++i]) || 30000;
        } else if (flag === '--topic') {
            topic = args[++i] || topic;
        } else if (flag === '--headless') {
            headless = true;
        } else if (flag === '--help' || flag === '-h') {
            showHelp();
            process.exit(0);
        }
    } else {
        if (!profileName || profileName === 'profile1') {
            profileName = args[i];
        }
    }
}

function showHelp() {
    console.log(`
Usage: node gemini-automation-ax.js [profile] [options]

Arguments:
  profile              Chrome profile name (default: profile1)

Options:
  -q, --questions FILE Questions YAML file (default: inputs/gemini.yml)
  --wait-between MS    Milliseconds to wait between questions (default: 3000)
  --wait-response MS   Max milliseconds to wait for response (default: 30000)
  --topic TEXT         Replace {topic} in questions (default: latest AI agent automation development for past 1 week)
  --ax-watch N         Capture AX tree every N milliseconds
  --ax-files           Save AX snapshots to separate files
  --ax-roles R         Filter AX tree by roles (comma-separated)
  --ax-cdp             Use raw CDP instead of Playwright's snapshot
  --headless           Run Chrome in headless mode (default: false)
  -h, --help           Show this help message

YAML File Format:
  questions:
    - "What is machine learning?"
    - "Explain quantum computing"
    - "Best practices for API design"

Examples:
  node gemini-automation-ax.js profile1
  node gemini-automation-ax.js profile1 --questions my-questions.yml
  node gemini-automation-ax.js profile1 --wait-between 5000 --wait-response 60000
  node gemini-automation-ax.js profile1 --ax-files --ax-cdp
`);
}

const url = 'https://gemini.google.com';

function slugify(urlStr) {
    try {
        const u = new URL(urlStr);
        return u.hostname.replace(/[^a-z0-9]/gi, '_');
    } catch (e) {
        return urlStr.replace(/[^a-z0-9]/gi, '_');
    }
}

function getTimestamp() {
    const now = new Date();
    const pad = n => n.toString().padStart(2, '0');
    const yyyy = now.getFullYear();
    const mm = pad(now.getMonth() + 1);
    const dd = pad(now.getDate());
    const HH = pad(now.getHours());
    const MM = pad(now.getMinutes());
    const SS = pad(now.getSeconds());
    return `${yyyy}${mm}${dd}_${HH}${MM}${SS}`;
}

const slug = slugify(url);
const timeStr = getTimestamp();
const filename = `gemini_${timeStr}.jsonl`;
const outputDir = path.join(__dirname, 'payload');
const outputPath = path.join(outputDir, filename);
const axDir = axFiles ? path.join(outputDir, 'ax_snapshots', `gemini_${timeStr}`) : null;

if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir);
}
if (axDir && !fs.existsSync(axDir)) {
    fs.mkdirSync(axDir, {
        recursive: true
    });
}

const manager = new ChromeProfileManager();
let axSnapshotCount = 0;
let questionCount = 0;

function loadQuestions(filepath) {
    try {
        const fileContent = fs.readFileSync(filepath, 'utf8');
        const data = yaml.load(fileContent);

        if (!data.questions || !Array.isArray(data.questions)) {
            throw new Error('YAML file must contain a "questions" array');
        }

        return data.questions.map(question => {
            if (typeof question !== 'string') return question;
            return question.replace(/\{topic\}/g, topic);
        });
    } catch (e) {
        console.error(`Error loading questions file: ${e.message}`);
        console.log('\nExpected format:');
        console.log('questions:');
        console.log('  - "Question 1"');
        console.log('  - "Question 2"');
        process.exit(1);
    }
}

async function startProfile(name, isHeadless) {
    console.log(`Starting profile ${name}...`);
    try {
        const scriptPath = path.join(__dirname, 'chrome-profile-manager.sh');
        let command = `"${scriptPath}" start ${name}`;
        if (isHeadless) {
            command += ' --headless';
        }
        execSync(command, {
            stdio: 'inherit'
        });
        console.log('Waiting for Chrome to initialize...');
        await new Promise(r => setTimeout(r, 3000));
    } catch (e) {
        console.error('Error starting profile (might already be running):', e.message);
    }
}

function filterAxTreeByRoles(node, roles) {
    if (!node) return null;

    const filtered = {
        ...node
    };
    const keepNode = !roles || roles.includes(node.role);

    if (node.children && node.children.length > 0) {
        filtered.children = node.children
            .map(child => filterAxTreeByRoles(child, roles))
            .filter(child => child !== null);
    }

    if (!keepNode && (!filtered.children || filtered.children.length === 0)) {
        return null;
    }

    return filtered;
}

async function captureAxTreePlaywright(page) {
    try {
        if (!page.accessibility || typeof page.accessibility.snapshot !== 'function') {
            return null;
        }
        const snapshot = await page.accessibility.snapshot();
        return snapshot;
    } catch (e) {
        return null;
    }
}

async function captureAxTreeCDP(page) {
    try {
        const client = await page.context().newCDPSession(page);
        await client.send('Accessibility.enable');
        const result = await client.send('Accessibility.getFullAXTree');
        await client.send('Accessibility.disable');
        await client.detach();
        return result.nodes || result;
    } catch (e) {
        console.error('Error capturing AX tree (CDP):', e.message);
        return null;
    }
}

async function captureAxTree(page, stream, label = 'initial') {
    axSnapshotCount++;
    const timestamp = new Date().toISOString();

    let tree;
    let usedMethod = axMethod;

    if (axMethod === 'cdp') {
        tree = await captureAxTreeCDP(page);
    } else {
        tree = await captureAxTreePlaywright(page);
        if (!tree) {
            tree = await captureAxTreeCDP(page);
            usedMethod = 'cdp';
        }
    }

    if (!tree) {
        console.error('  ⚠ Failed to capture AX tree');
        return;
    }

    if (axRoles && usedMethod === 'playwright') {
        tree = filterAxTreeByRoles(tree, axRoles);
    }

    const data = {
        type: 'accessibility',
        method: usedMethod,
        snapshot_id: axSnapshotCount,
        question_id: questionCount,
        label: label,
        timestamp: timestamp,
        tree: tree
    };

    stream.write(JSON.stringify(data) + '\n');

    if (axFiles && axDir) {
        const axFilename = `ax_${axSnapshotCount}_q${questionCount}_${label}_${Date.now()}.json`;
        const axPath = path.join(axDir, axFilename);
        fs.writeFileSync(axPath, JSON.stringify(data, null, 2));
    }

    console.log(`  ✓ Captured AX tree #${axSnapshotCount} (${countNodes(tree)} nodes)`);
}

function countNodes(node) {
    if (!node) return 0;
    if (Array.isArray(node)) return node.reduce((sum, n) => sum + countNodes(n), 0);
    let count = 1;
    if (node.children) {
        count += node.children.reduce((sum, child) => sum + countNodes(child), 0);
    }
    return count;
}

async function waitForResponseComplete(page, timeout = 30000) {
    console.log('  ⏳ Waiting for response...');

    try {
        await new Promise(r => setTimeout(r, 2000));

        const answerComplete = await page.evaluate((maxTimeout) => {
            return new Promise((resolve) => {
                // Gemini-specific selectors for response containers
                const containerSelectors = [
                    '[data-testid="conversation-turn"]',
                    '.response-container',
                    '.model-response',
                    '[data-message-id]',
                    'main',
                    'div[role="main"]',
                    '.chat-container',
                    'body'
                ];

                let container = null;
                for (const sel of containerSelectors) {
                    container = document.querySelector(sel);
                    if (container) break;
                }

                if (!container) {
                    resolve(false);
                    return;
                }

                let lastText = container.innerText || '';
                let stableCount = 0;
                let changeDetected = false;

                const observer = new MutationObserver(() => {
                    const currentText = container.innerText || '';
                    if (currentText !== lastText) {
                        changeDetected = true;
                        stableCount = 0;
                        lastText = currentText;
                    } else if (changeDetected) {
                        stableCount++;
                        if (stableCount >= 5) {
                            observer.disconnect();
                            resolve(true);
                        }
                    }
                });

                observer.observe(container, {
                    childList: true,
                    subtree: true,
                    characterData: true
                });

                const checkInterval = setInterval(() => {
                    const currentText = container.innerText || '';
                    if (currentText !== lastText) {
                        changeDetected = true;
                        stableCount = 0;
                        lastText = currentText;
                    } else if (changeDetected) {
                        stableCount++;
                        if (stableCount >= 5) {
                            clearInterval(checkInterval);
                            observer.disconnect();
                            resolve(true);
                        }
                    }
                }, 500);

                setTimeout(() => {
                    clearInterval(checkInterval);
                    observer.disconnect();
                    resolve(changeDetected);
                }, maxTimeout);
            });
        }, timeout - 2000);

        if (answerComplete) {
            console.log('  ✓ Response complete');
            return true;
        } else {
            console.log('  ⚠ Timeout or no response detected');
            return false;
        }
    } catch (e) {
        console.error('  ✗ Error waiting for response:', e.message);
        return false;
    }
}

async function askQuestion(page, question, stream) {
    questionCount++;

    console.log(`\n${'─'.repeat(60)}`);
    console.log(`Question ${questionCount}: ${question}`);
    console.log('─'.repeat(60));

    const questionData = {
        type: 'question',
        question_id: questionCount,
        question: question,
        timestamp: new Date().toISOString()
    };
    stream.write(JSON.stringify(questionData) + '\n');

    try {
        console.log('  → Finding input field...');
        // Gemini-specific input selectors
        const inputSelectors = [
            'textarea[placeholder*="Ask"]',
            'textarea[placeholder*="Enter"]',
            'textarea[aria-label*="Ask"]',
            'textarea[aria-label*="Message"]',
            'div[contenteditable="true"]',
            '[contenteditable="true"]',
            'rich-textarea',
            'textarea',
            'input[type="text"]'
        ];

        let inputElement = null;
        let usedSelector = null;

        for (const selector of inputSelectors) {
            try {
                inputElement = await page.waitForSelector(selector, {
                    timeout: 5000
                });
                if (inputElement) {
                    usedSelector = selector;
                    console.log(`  ✓ Found input: ${selector}`);
                    break;
                }
            } catch (e) {
                continue;
            }
        }

        if (!inputElement) {
            throw new Error('Could not find input field');
        }

        await page.evaluate((args) => {
            const el = document.querySelector(args.selector);
            if (el) {
                if (el.isContentEditable) {
                    el.textContent = '';
                } else if ('value' in el) {
                    el.value = '';
                }
            }
        }, {
            selector: usedSelector
        });

        await new Promise(r => setTimeout(r, 300));

        console.log('  → Typing question...');
        await page.evaluate((args) => {
            const el = document.querySelector(args.selector);
            if (!el) return;

            if (el.isContentEditable) {
                el.focus();
                el.textContent = args.text;
                el.dispatchEvent(new InputEvent('input', {
                    bubbles: true,
                    cancelable: true,
                    data: args.text,
                    inputType: 'insertText'
                }));
            } else if ('value' in el) {
                el.focus();
                el.value = args.text;
                el.dispatchEvent(new Event('input', {
                    bubbles: true
                }));
            }
        }, {
            selector: usedSelector,
            text: question
        });

        await new Promise(r => setTimeout(r, 500));

        console.log('  → Capturing pre-submit state...');
        await captureAxTree(page, stream, `q${questionCount}_before_submit`);

        console.log('  → Finding submit button...');
        // Gemini-specific submit button selectors
        const buttonSelectors = [
            'button[aria-label*="Send"]',
            'button[aria-label*="Submit"]',
            'button[type="submit"]',
            'button[data-testid*="send"]',
            'button.send-button',
            'button.submit-button',
            'button svg[icon="send"]',
            'button:has(svg)'
        ];

        let submitButton = null;
        let usedButtonSelector = null;

        for (const selector of buttonSelectors) {
            try {
                submitButton = await page.waitForSelector(selector, {
                    timeout: 3000,
                    state: 'visible'
                });
                if (submitButton) {
                    usedButtonSelector = selector;
                    console.log(`  ✓ Found button: ${selector}`);
                    break;
                }
            } catch (e) {
                continue;
            }
        }

        if (!submitButton) {
            console.log('  → Submit button not found, trying Enter key...');
            await page.evaluate((args) => {
                const el = document.querySelector(args.selector);
                if (el) el.focus();
            }, {
                selector: usedSelector
            });
            await page.keyboard.press('Enter');
        } else {
            console.log('  → Clicking submit button...');
            await submitButton.click();
        }

        const responseComplete = await waitForResponseComplete(page, waitForResponse);

        if (responseComplete) {
            console.log('  → Capturing response state...');
            await captureAxTree(page, stream, `q${questionCount}_after_response`);

            console.log('  → Extracting response...');
            const responseText = await page.evaluate(() => {
                // Gemini-specific response selectors
                const selectors = [
                    '[data-testid="conversation-turn"]',
                    '.response-container',
                    '.model-response',
                    '[data-message-id]',
                    'main',
                    'div[role="main"]',
                    '.chat-container'
                ];

                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText) {
                        return el.innerText;
                    }
                }

                return document.body.innerText;
            });

            const responseData = {
                type: 'response',
                question_id: questionCount,
                question: question,
                response: responseText.substring(0, 5000) + (responseText.length > 5000 ? '...' : ''),
                response_length: responseText.length,
                timestamp: new Date().toISOString()
            };
            stream.write(JSON.stringify(responseData) + '\n');

            console.log(`  ✓ Question ${questionCount} complete (response: ${responseText.length} chars)`);
        } else {
            console.log(`  ⚠ Question ${questionCount} may be incomplete`);
        }

        return true;
    } catch (e) {
        console.error(`  ✗ Error asking question: ${e.message}`);

        const errorData = {
            type: 'error',
            question_id: questionCount,
            question: question,
            error: e.message,
            timestamp: new Date().toISOString()
        };
        stream.write(JSON.stringify(errorData) + '\n');

        return false;
    }
}

async function main() {
    console.log(`\nLoading questions from: ${questionsFile}`);
    const questions = loadQuestions(questionsFile);
    console.log(`✓ Loaded ${questions.length} question(s)\n`);

    await startProfile(profileName, headless);

    console.log(`${'='.repeat(60)}`);
    console.log(`Profile: ${profileName}`);
    console.log(`Questions: ${questions.length}`);
    console.log(`Wait between: ${waitBetweenQuestions}ms`);
    console.log(`Wait for response: ${waitForResponse}ms`);
    console.log(`Output: ${outputPath}`);
    if (axFiles) console.log(`AX Files: ${axDir}`);
    console.log(`${'='.repeat(60)}\n`);

    const stream = fs.createWriteStream(outputPath, {
        flags: 'a'
    });

    const cleanup = async () => {
        console.log('\n\nStopping automation...');
        stream.end();
        await manager.disconnectAll();
        console.log(`\nComplete!`);
        console.log(`  Questions asked: ${questionCount}/${questions.length}`);
        console.log(`  Main file: ${outputPath}`);
        if (axFiles && axDir) {
            console.log(`  AX snapshots: ${axDir}/`);
        }
        console.log(`  Total AX snapshots: ${axSnapshotCount}\n`);
        process.exit(0);
    };

    process.on('SIGINT', cleanup);
    process.on('SIGTERM', cleanup);

    try {
        console.log(`Connecting to ${profileName}...`);
        const browser = await manager.connect(profileName);

        const contexts = browser.contexts();
        const context = contexts.length > 0 ? contexts[0] : await browser.newContext();
        const page = await context.newPage();

        console.log(`Navigating to ${url}...`);

        page.on('request', request => {
            try {
                const data = {
                    type: 'request',
                    timestamp: new Date().toISOString(),
                    url: request.url(),
                    method: request.method(),
                    headers: request.headers()
                };
                stream.write(JSON.stringify(data) + '\n');
            } catch (e) {}
        });

        page.on('response', async response => {
            try {
                let body = null;
                const resourceType = response.request().resourceType();
                const contentType = response.headers()['content-type'] || '';

                if (['xhr', 'fetch'].includes(resourceType) || contentType.includes('json')) {
                    try {
                        body = await response.text();
                    } catch (e) {
                        body = '[Body unavailable]';
                    }
                }

                const data = {
                    type: 'response',
                    timestamp: new Date().toISOString(),
                    url: response.url(),
                    status: response.status(),
                    body: body
                };
                stream.write(JSON.stringify(data) + '\n');
            } catch (e) {}
        });

        // await page.goto(url, {
        //     waitUntil: 'networkidle',
        //     timeout: 90000
        // });

        await page.goto(url, {
            waitUntil: 'domcontentloaded', // This triggers much faster
            timeout: 60000
        });

        // Instead of waiting for network idle, wait for the specific input element
        console.log('Waiting for Gemini interface to be ready...');
        const inputSelectors = [
            'textarea[placeholder*="Ask"]',
            'div[contenteditable="true"]',
            'rich-textarea'
        ];

        // Wait for at least one of these to appear
        await Promise.race(inputSelectors.map(s => page.waitForSelector(s, {
            timeout: 30000
        })));

        console.log('✓ Page loaded');
        await new Promise(r => setTimeout(r, 3000)); // Brief pause for UI stability

        console.log('Capturing initial page state...');
        await captureAxTree(page, stream, 'initial_load');

        await new Promise(r => setTimeout(r, 2000));

        for (let i = 0; i < questions.length; i++) {
            const question = questions[i];
            await askQuestion(page, question, stream);

            if (i < questions.length - 1) {
                console.log(`\n  ⏸  Waiting ${waitBetweenQuestions}ms before next question...`);
                await new Promise(r => setTimeout(r, waitBetweenQuestions));
            }
        }

        console.log('\n' + '='.repeat(60));
        console.log(`All ${questions.length} questions completed!`);
        console.log('='.repeat(60));

        await cleanup();
    } catch (err) {
        console.error('\n✗ Error:', err);
        stream.end();
        process.exit(1);
    }
}

main();