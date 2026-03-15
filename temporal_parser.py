"""
Temporal Parser Module for LiteLLM Proxy.

This module parses temporal expressions in user queries and converts them
to date ranges for more relevant search results.

Examples:
    - "past week" -> {"days": 7}
    - "last month" -> {"months": 1}
    - "yesterday" -> {"days": 1}
    - "recent news" -> {"days": 7}
    - "2024" -> {"year": 2024}
    - "this year" -> {"year": 2025}
"""

import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta
import logging

logger = logging.getLogger("temporal_parser")

# Current time reference (can be mocked for testing)
_current_time: Optional[datetime] = None

def get_current_time() -> datetime:
    """Get the current reference time."""
    global _current_time
    if _current_time is None:
        _current_time = datetime.now()
    return _current_time

def set_current_time(dt: datetime):
    """Set a custom current time (useful for testing)."""
    global _current_time
    _current_time = dt

def reset_current_time():
    """Reset to use system current time."""
    global _current_time
    _current_time = None


class TemporalParser:
    """
    Parser for temporal expressions in natural language.
    
    Supports:
    - Relative time: "past week", "last month", "yesterday", "recent"
    - Absolute years: "in 2024", "2025 news"
    - Specific dates: "January 2025", "last Tuesday"
    """
    
    # Patterns for temporal expressions (ORDER MATTERS - more specific first)
    PATTERNS = [
        # Specific time units first (more specific patterns)
        (r'\b(yesterday)\b', 'day', 1),
        (r'\b(today)\b', 'day', 0),
        (r'\b(just now)\b', 'minute', 0),
        
        # Days ago - must check before general "past"
        (r'\b(\d+)\s*days?\s*ago\b', 'days', None),
        
        # Weeks ago - must check before general "past"  
        (r'\b(\d+)\s*weeks?\s*ago\b', 'weeks', None),
        
        # Months ago - must check before general "past"
        (r'\b(\d+)\s*months?\s*ago\b', 'months', None),
        
        # Years ago
        (r'\b(\d+)\s*years?\s*ago\b', 'years', None),
        
        # "Past X days/weeks/months/years" patterns
        (r'\b(past|last)\s*(\d+)\s*days?\b', 'days', None),
        (r'\b(past|last)\s*(\d+)\s*weeks?\b', 'weeks', None),
        (r'\b(past|last)\s*(\d+)\s*months?\b', 'months', None),
        (r'\b(past|last)\s*(\d+)\s*years?\b', 'years', None),
        
        # Singular "past week/month/year"
        (r'\b(past|last)\s*week\b', 'weeks', 1),
        (r'\b(past|last)\s*month\b', 'months', 1),
        (r'\b(past|last)\s*year\b', 'years', 1),
        
        # "Recent" expressions
        (r'\b(recent(ly)?)\b', 'days', 7),
        (r'\b(latest|latest news)\b', 'days', 7),
        (r'\b(breaking|breaking news)\b', 'days', 1),
        
        # This/next time
        (r'\b(this|these)\s*(week|month|year)\b', 'this', None),
        (r'\b(last|past)\s*(week|month|year)\b', 'past', None),
    ]
    
    # Year patterns
    YEAR_PATTERN = r'\b(20\d{2}|20\d{1}\d{2})\b'
    
    def __init__(self):
        self.current = get_current_time()
    
    def parse(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse temporal expression from text.
        
        Args:
            text: Input text to parse
            
        Returns:
            Dictionary with temporal info or None if no temporal expression found
        """
        text_lower = text.lower()
        
        # Check for year references first
        year_match = re.search(self.YEAR_PATTERN, text)
        if year_match:
            year = int(year_match.group(1))
            return {
                "type": "year",
                "year": year,
                "description": f"year {year}",
                "time_range": self._get_year_range(year)
            }
        
        # Check patterns
        for pattern, unit, value in self.PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                # Extract numeric value if present
                if value is None and len(match.groups()) > 1:
                    try:
                        value = int(match.group(2) or match.group(1))
                    except (ValueError, IndexError):
                        value = 1
                
                return self._build_result(unit, value, text_lower)
        
        return None
    
    def _build_result(self, unit: str, value: int, text: str) -> Dict[str, Any]:
        """Build result dictionary from parsed values."""
        if unit == 'this':
            return self._handle_this(value, text)
        elif unit == 'past':
            return self._handle_past(value, text)
        
        return {
            "type": "relative",
            "unit": unit,
            "value": value,
            "description": self._describe(unit, value),
            "time_range": self._calculate_range(unit, value)
        }
    
    def _handle_this(self, unit: str, text: str) -> Dict[str, Any]:
        """Handle 'this week/month/year' expressions."""
        if unit == 'week':
            start = self.current - timedelta(days=self.current.weekday())
            return {
                "type": "this_week",
                "unit": "week",
                "value": 0,
                "description": "this week",
                "time_range": (start, self.current)
            }
        elif unit == 'month':
            start = self.current.replace(day=1)
            return {
                "type": "this_month", 
                "unit": "month",
                "value": 0,
                "description": "this month",
                "time_range": (start, self.current)
            }
        else:  # year
            start = self.current.replace(month=1, day=1)
            return {
                "type": "this_year",
                "unit": "year",
                "value": 0,
                "description": "this year",
                "time_range": (start, self.current)
            }
    
    def _handle_past(self, unit: str, text: str) -> Dict[str, Any]:
        """Handle 'past/last week/month/year' expressions."""
        if unit == 'week':
            return {
                "type": "past_week",
                "unit": "weeks",
                "value": 1,
                "description": "past week",
                "time_range": self._calculate_range("weeks", 1)
            }
        elif unit == 'month':
            return {
                "type": "past_month",
                "unit": "months",
                "value": 1,
                "description": "past month",
                "time_range": self._calculate_range("months", 1)
            }
        else:  # year
            return {
                "type": "past_year",
                "unit": "years",
                "value": 1,
                "description": "past year",
                "time_range": self._calculate_range("years", 1)
            }
    
    def _calculate_range(self, unit: str, value: int) -> Tuple[datetime, datetime]:
        """Calculate date range from now."""
        if unit == 'minute':
            start = self.current - timedelta(minutes=value)
        elif unit == 'hour':
            start = self.current - timedelta(hours=value)
        elif unit == 'day':
            start = self.current - timedelta(days=value)
        elif unit == 'week':
            start = self.current - timedelta(weeks=value)
        elif unit == 'month':
            start = self.current - relativedelta(months=value)
        elif unit == 'year':
            start = self.current - relativedelta(years=value)
        else:
            start = self.current - timedelta(days=7)
        
        return (start, self.current)
    
    def _get_year_range(self, year: int) -> Tuple[datetime, datetime]:
        """Get range for a specific year."""
        start = datetime(year, 1, 1)
        end = datetime(year, 12, 31, 23, 59, 59)
        return (start, end)
    
    def _describe(self, unit: str, value: int) -> str:
        """Get human-readable description."""
        if value == 0:
            return f"this {unit}"
        elif value == 1:
            return f"past {unit}" if unit != 'day' else "yesterday"
        else:
            return f"past {value} {unit}"
    
    def format_for_search(self, temporal_info: Dict[str, Any]) -> str:
        """
        Format temporal info as a search modifier.
        
        Args:
            temporal_info: Result from parse()
            
        Returns:
            String to append to search query with timestamp details
        """
        if not temporal_info:
            return ""
        
        t_type = temporal_info.get("type")
        
        # Get time range for precise timestamps
        time_range = temporal_info.get("time_range")
        if time_range:
            start_date, end_date = time_range
            
            if t_type == "year":
                year = temporal_info.get("year")
                return f" since:{year}-01-01 until:{year}-12-31"
            else:
                start_str = start_date.strftime("%Y-%m-%d")
                end_str = end_date.strftime("%Y-%m-%d")
                
                # For very recent (today/yesterday), use timelimit
                if temporal_info.get("value", 0) == 0:
                    return f" timelimit:d"
                
                return f" since:{start_str} until:{end_str}"
        
        # Fallback to simple timelimit
        unit = temporal_info.get("unit", "day")
        value = temporal_info.get("value", 7)
        
        timelimit_map = {
            "day": "d",
            "week": "w", 
            "month": "m",
            "year": "y"
        }
        
        timelimit = timelimit_map.get(unit, "w")
        
        if value <= 1:
            return f" timelimit:{timelimit}"
        else:
            return f" timelimit:{timelimit}"
    
    def format_query_modifier(self, temporal_info: Dict[str, Any]) -> str:
        """
        Format temporal info as a precise timestamp-based query modifier.
        
        Args:
            temporal_info: Result from parse()
            
        Returns:
            Query prefix string with precise dates
        """
        if not temporal_info:
            return ""
        
        t_type = temporal_info.get("type")
        
        # Get time range
        time_range = temporal_info.get("time_range")
        if not time_range:
            return ""
        
        start_date, end_date = time_range
        
        # Format dates as YYYY-MM-DD
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        if t_type == "year":
            # For year references, just use the year
            year = temporal_info.get("year")
            return f"[{year}]"
        
        # For relative time, use date range
        if start_str == end_str:
            return f"[{start_str}]"
        else:
            return f"[{start_str} TO {end_str}]"


# Singleton instance
_temporal_parser: Optional[TemporalParser] = None

def get_temporal_parser() -> TemporalParser:
    """Get or create the singleton TemporalParser instance."""
    global _temporal_parser
    if _temporal_parser is None:
        _temporal_parser = TemporalParser()
    return _temporal_parser


def parse_temporal(text: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function to parse temporal expression from text.
    
    Args:
        text: Input text to parse
        
    Returns:
        Temporal info dict or None
    """
    parser = get_temporal_parser()
    return parser.parse(text)


def format_for_search(text: str) -> str:
    """
    Parse text and return search modifier.
    
    Args:
        text: Input text with potential temporal expression
        
    Returns:
        Search modifier string
    """
    temporal_info = parse_temporal(text)
    parser = get_temporal_parser()
    return parser.format_for_search(temporal_info)


if __name__ == "__main__":
    # Test the module
    logging.basicConfig(level=logging.INFO)
    
    test_queries = [
        "what happened yesterday",
        "news about AI past week",
        "latest Python release last month",
        "2024 technology trends",
        "recent climate change news",
        "past 3 months stock market",
        "what is the weather today",
        "breaking news",
        "this year best movies"
    ]
    
    parser = TemporalParser()
    
    print("=" * 60)
    print("TEMPORAL PARSER TEST")
    print("=" * 60)
    
    for query in test_queries:
        result = parser.parse(query)
        search_mod = parser.format_for_search(result) if result else ""
        print(f"\n📝 Query: {query}")
        if result:
            print(f"   → {result['description']}")
            print(f"   → Search modifier: '{search_mod}'")
        else:
            print(f"   → No temporal expression found")
