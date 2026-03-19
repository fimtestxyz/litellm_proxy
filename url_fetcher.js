const { chromium } = require('playwright');
const { Readability } = require('@mozilla/readability');
const { JSDOM } = require('jsdom');
const TurndownService = require('turndown');
const fs = require('fs');
const path = require('path');
const { program } = require('commander');

/**
 * Fetch URL content and convert to Markdown.
 * @param {string} url - The URL to fetch.
 * @param {object} options - Options for fetching and conversion.
 * @returns {Promise<object>} - Result with markdown and metadata.
 */
async function fetchToMarkdown(url, options = {}) {
  const {
    timeout = 30000,
    userAgent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    headless = true
  } = options;

  let browser;
  try {
    browser = await chromium.launch({ headless });
    const context = await browser.newContext({
      userAgent,
      viewport: { width: 1280, height: 800 }
    });
    
    const page = await context.newPage();
    
    // Set a longer timeout for navigation
    await page.goto(url, { 
      waitUntil: 'networkidle', 
      timeout 
    });

    // Get the HTML content
    const html = await page.content();
    const title = await page.title();
    
    // Use JSDOM and Readability to extract main content
    const dom = new JSDOM(html, { url });
    const reader = new Readability(dom.window.document);
    const article = reader.parse();

    if (!article) {
      throw new Error('Failed to parse content with Readability');
    }

    // Convert HTML to Markdown
    const turndownService = new TurndownService({
      headingStyle: 'atx',
      codeBlockStyle: 'fenced'
    });
    
    // Custom rules for turndown if needed
    turndownService.addRule('remove-scripts', {
      filter: ['script', 'style', 'iframe', 'noscript'],
      replacement: () => ''
    });

    const markdown = turndownService.turndown(article.content);
    
    return {
      url,
      title: article.title || title,
      byline: article.byline,
      excerpt: article.excerpt,
      siteName: article.siteName,
      content: markdown,
      length: markdown.length,
      fetchedAt: new Date().toISOString()
    };
  } catch (error) {
    console.error(`Error fetching ${url}:`, error.message);
    throw error;
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

// CLI usage
if (require.main === module) {
  program
    .argument('<url>', 'URL to fetch')
    .option('-o, --output <path>', 'Output file path')
    .option('--timeout <ms>', 'Timeout in milliseconds', 30000)
    .option('--no-headless', 'Run in headful mode')
    .action(async (url, options) => {
      try {
        const result = await fetchToMarkdown(url, {
          timeout: parseInt(options.timeout),
          headless: options.headless
        });

        const output = `# ${result.title}\n\n` +
          `Source: ${result.url}\n` +
          `Fetched: ${result.fetchedAt}\n\n` +
          `---\n\n` +
          result.content;

        if (options.output) {
          fs.writeFileSync(options.output, output);
          console.log(`Saved to ${options.output}`);
        } else {
          console.log(output);
        }
      } catch (error) {
        process.exit(1);
      }
    });

  program.parse();
}

module.exports = { fetchToMarkdown };
