"""
Advanced analysis tools for Gmail data insights.

This module provides specialized CrewAI tools for Gmail email analysis
focused on SQL query generation and execution.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
import statistics
from collections import defaultdict, Counter

from crewai.tools import BaseTool

from .constants import DATABASE_FILE_NAME


# EmailPatternAnalyzer class removed - not needed for simple Gmail Q&A
