"""
Advanced analysis tools for Gmail data insights.

This module provides specialized CrewAI tools for deeper email analysis
beyond basic SQL queries, including pattern recognition, sentiment analysis,
and relationship mapping.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
import statistics
from collections import defaultdict, Counter

from crewai.tools import BaseTool

from .constants import DATABASE_FILE_NAME


class EmailPatternAnalyzer(BaseTool):
    """Advanced email pattern analysis tool for identifying trends and insights."""

    name: str = "Email Pattern Analyzer"
    description: str = """
    Analyze complex email patterns and trends in your Gmail data.
    
    This tool provides advanced analytics beyond basic SQL queries:
    - Volume trends and seasonal patterns
    - Response time analysis and communication cadence
    - Email size and attachment patterns
    - Activity distribution (hourly, daily, weekly patterns)
    - Communication network analysis
    - Thread depth and conversation patterns
    
    Use this tool when you need sophisticated analysis like:
    - "What are my email volume trends over the past year?"
    - "How has my response time changed over time?"
    - "When am I most active in email during the day/week?"
    - "Which contacts do I have the longest conversations with?"
    """

    def __init__(self, db_path: str, **kwargs):
        super().__init__(**kwargs)
        self._db_path = db_path
        self._analysis_cache = {}

    def _run(self, analysis_type: str, **parameters) -> str:
        """
        Perform email pattern analysis.

        Args:
            analysis_type: Type of analysis to perform
                - 'volume_trends': Email volume over time
                - 'response_times': Response time analysis
                - 'activity_patterns': When you're most active
                - 'thread_analysis': Conversation depth analysis
                - 'network_analysis': Communication network insights

        Returns:
            Formatted analysis results with insights
        """
        try:
            if analysis_type == "volume_trends":
                return self._analyze_volume_trends(**parameters)
            elif analysis_type == "response_times":
                return self._analyze_response_times(**parameters)
            elif analysis_type == "activity_patterns":
                return self._analyze_activity_patterns(**parameters)
            elif analysis_type == "thread_analysis":
                return self._analyze_thread_patterns(**parameters)
            elif analysis_type == "network_analysis":
                return self._analyze_communication_network(**parameters)
            else:
                return f"Unknown analysis type: {analysis_type}. Available types: volume_trends, response_times, activity_patterns, thread_analysis, network_analysis"

        except Exception as e:
            return f"Error in pattern analysis: {str(e)}"

    def _analyze_volume_trends(
        self, period: str = "monthly", time_range: Optional[str] = None
    ) -> str:
        """Analyze email volume trends over time."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            # Determine time grouping based on period
            if period == "daily":
                date_format = "%Y-%m-%d"
                group_by = "DATE(timestamp)"
            elif period == "weekly":
                date_format = "%Y-W%W"
                group_by = "strftime('%Y-W%W', timestamp)"
            elif period == "monthly":
                date_format = "%Y-%m"
                group_by = "strftime('%Y-%m', timestamp)"
            elif period == "yearly":
                date_format = "%Y"
                group_by = "strftime('%Y', timestamp)"
            else:
                return f"Invalid period: {period}. Use: daily, weekly, monthly, yearly"

            # Add time range filter if specified
            time_filter = ""
            if time_range:
                if time_range == "last_year":
                    time_filter = "AND timestamp >= date('now', '-1 year')"
                elif time_range == "last_6_months":
                    time_filter = "AND timestamp >= date('now', '-6 months')"
                elif time_range == "last_month":
                    time_filter = "AND timestamp >= date('now', '-1 month')"

            query = f"""
            SELECT {group_by} as period,
                   COUNT(*) as total_emails,
                   COUNT(CASE WHEN is_outgoing = 1 THEN 1 END) as sent_emails,
                   COUNT(CASE WHEN is_outgoing = 0 THEN 1 END) as received_emails,
                   AVG(size) as avg_size
            FROM messages 
            WHERE 1=1 {time_filter}
            GROUP BY {group_by}
            ORDER BY period DESC
            LIMIT 50
            """

            cursor.execute(query)
            results = cursor.fetchall()
            conn.close()

            if not results:
                return "No email data found for analysis."

            # Calculate trends and insights
            total_volumes = [row[1] for row in results]
            avg_volume = statistics.mean(total_volumes)
            trend_direction = (
                "increasing" if total_volumes[0] > total_volumes[-1] else "decreasing"
            )

            # Format results
            analysis = [
                f"📊 Email Volume Trends ({period.title()}) - {time_range or 'All time'}",
                f"Average {period} volume: {avg_volume:.1f} emails",
                f"Overall trend: {trend_direction}",
                "",
                "Period | Total | Sent | Received | Avg Size",
                "-" * 45,
            ]

            for row in results[:10]:  # Show top 10 periods
                period_str, total, sent, received, avg_size = row
                analysis.append(
                    f"{period_str} | {total:5d} | {sent:4d} | {received:8d} | {avg_size:8.0f}"
                )

            if len(results) > 10:
                analysis.append(f"... and {len(results) - 10} more periods")

            # Add insights
            analysis.extend(
                [
                    "",
                    "🔍 Insights:",
                    f"• Peak volume: {max(total_volumes)} emails",
                    f"• Lowest volume: {min(total_volumes)} emails",
                    f"• Trend: Volume is {trend_direction} over time",
                ]
            )

            return "\n".join(analysis)

        except Exception as e:
            return f"Error analyzing volume trends: {str(e)}"

    def _analyze_response_times(self, contact_filter: Optional[str] = None) -> str:
        """Analyze email response time patterns."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            # Query to calculate response times between emails in threads
            contact_condition = ""
            if contact_filter:
                contact_condition = f"AND sender->>'$.email' LIKE '%{contact_filter}%'"

            query = f"""
            WITH email_pairs AS (
                SELECT 
                    thread_id,
                    timestamp,
                    sender->>'$.email' as sender_email,
                    is_outgoing,
                    LAG(timestamp) OVER (PARTITION BY thread_id ORDER BY timestamp) as prev_timestamp,
                    LAG(is_outgoing) OVER (PARTITION BY thread_id ORDER BY timestamp) as prev_outgoing
                FROM messages
                WHERE thread_id IS NOT NULL {contact_condition}
            )
            SELECT 
                sender_email,
                AVG((julianday(timestamp) - julianday(prev_timestamp)) * 24 * 60) as avg_response_minutes,
                COUNT(*) as response_count,
                MIN((julianday(timestamp) - julianday(prev_timestamp)) * 24 * 60) as min_response_minutes,
                MAX((julianday(timestamp) - julianday(prev_timestamp)) * 24 * 60) as max_response_minutes
            FROM email_pairs
            WHERE prev_timestamp IS NOT NULL 
              AND is_outgoing != prev_outgoing  -- Only count actual responses
              AND (julianday(timestamp) - julianday(prev_timestamp)) * 24 * 60 BETWEEN 1 AND 10080  -- 1 min to 1 week
            GROUP BY sender_email
            HAVING response_count >= 3
            ORDER BY avg_response_minutes ASC
            LIMIT 20
            """

            cursor.execute(query)
            results = cursor.fetchall()
            conn.close()

            if not results:
                return (
                    "No response time data found. This requires threaded conversations."
                )

            # Format results with insights
            analysis = [
                "⏱️ Email Response Time Analysis",
                "",
                "Contact | Avg Response | Responses | Min | Max",
                "-" * 55,
            ]

            all_response_times = []
            for row in results:
                email, avg_minutes, count, min_minutes, max_minutes = row
                avg_hours = avg_minutes / 60
                min_hours = min_minutes / 60
                max_hours = max_minutes / 60

                all_response_times.append(avg_minutes)

                # Format time display
                if avg_hours < 1:
                    avg_display = f"{avg_minutes:.0f}m"
                elif avg_hours < 24:
                    avg_display = f"{avg_hours:.1f}h"
                else:
                    avg_display = f"{avg_hours/24:.1f}d"

                analysis.append(
                    f"{email[:25]:25} | {avg_display:11} | {count:9d} | {min_hours:.1f}h | {max_hours:.1f}h"
                )

            # Add insights
            overall_avg = statistics.mean(all_response_times)
            analysis.extend(
                [
                    "",
                    "🔍 Insights:",
                    f"• Overall average response time: {overall_avg/60:.1f} hours",
                    f"• Fastest responders: {results[0][0]} ({results[0][1]/60:.1f}h avg)",
                    f"• Total contacts analyzed: {len(results)}",
                ]
            )

            return "\n".join(analysis)

        except Exception as e:
            return f"Error analyzing response times: {str(e)}"

    def _analyze_activity_patterns(self, granularity: str = "hourly") -> str:
        """Analyze when you're most active in email."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            if granularity == "hourly":
                query = """
                SELECT strftime('%H', timestamp) as hour,
                       COUNT(*) as email_count,
                       COUNT(CASE WHEN is_outgoing = 1 THEN 1 END) as sent_count,
                       COUNT(CASE WHEN is_outgoing = 0 THEN 1 END) as received_count
                FROM messages
                GROUP BY hour
                ORDER BY hour
                """
                time_label = "Hour"
            elif granularity == "daily":
                query = """
                SELECT 
                    CASE strftime('%w', timestamp)
                        WHEN '0' THEN 'Sunday'
                        WHEN '1' THEN 'Monday'  
                        WHEN '2' THEN 'Tuesday'
                        WHEN '3' THEN 'Wednesday'
                        WHEN '4' THEN 'Thursday'
                        WHEN '5' THEN 'Friday'
                        WHEN '6' THEN 'Saturday'
                    END as day_name,
                    strftime('%w', timestamp) as day_num,
                    COUNT(*) as email_count,
                    COUNT(CASE WHEN is_outgoing = 1 THEN 1 END) as sent_count
                FROM messages
                GROUP BY day_num
                ORDER BY day_num
                """
                time_label = "Day"
            else:
                return f"Invalid granularity: {granularity}. Use: hourly, daily"

            cursor.execute(query)
            results = cursor.fetchall()
            conn.close()

            if not results:
                return "No activity data found."

            # Find peak activity times
            if granularity == "hourly":
                peak_hour = max(results, key=lambda x: x[1])
                analysis = [
                    "📅 Email Activity Patterns (Hourly)",
                    f"Peak activity: {peak_hour[0]}:00 with {peak_hour[1]} emails",
                    "",
                    "Hour | Total | Sent | Received",
                    "-" * 30,
                ]

                for row in results:
                    hour, total, sent, received = row
                    analysis.append(
                        f"{hour:2s}:00 | {total:5d} | {sent:4d} | {received:8d}"
                    )

            else:  # daily
                peak_day = max(results, key=lambda x: x[2])
                analysis = [
                    "📅 Email Activity Patterns (Daily)",
                    f"Peak activity: {peak_day[0]} with {peak_day[2]} emails",
                    "",
                    "Day | Total | Sent",
                    "-" * 20,
                ]

                for row in results:
                    day_name, _, total, sent = row
                    analysis.append(f"{day_name:9} | {total:5d} | {sent:4d}")

            return "\n".join(analysis)

        except Exception as e:
            return f"Error analyzing activity patterns: {str(e)}"

    def _analyze_thread_patterns(self) -> str:
        """Analyze email thread depth and conversation patterns."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            query = """
            SELECT 
                thread_id,
                COUNT(*) as message_count,
                COUNT(DISTINCT sender->>'$.email') as unique_participants,
                MIN(timestamp) as thread_start,
                MAX(timestamp) as thread_end,
                (julianday(MAX(timestamp)) - julianday(MIN(timestamp))) as duration_days
            FROM messages
            WHERE thread_id IS NOT NULL
            GROUP BY thread_id
            HAVING message_count > 1
            ORDER BY message_count DESC
            LIMIT 20
            """

            cursor.execute(query)
            results = cursor.fetchall()
            conn.close()

            if not results:
                return "No thread data found."

            # Calculate statistics
            message_counts = [row[1] for row in results]
            avg_thread_length = statistics.mean(message_counts)

            analysis = [
                "🧵 Email Thread Analysis",
                f"Average thread length: {avg_thread_length:.1f} messages",
                "",
                "Thread ID | Messages | Participants | Duration",
                "-" * 45,
            ]

            for row in results[:10]:
                thread_id, msg_count, participants, start, end, duration = row
                duration_str = (
                    f"{duration:.1f}d" if duration > 1 else f"{duration*24:.1f}h"
                )
                analysis.append(
                    f"{thread_id[:12]:12} | {msg_count:8d} | {participants:12d} | {duration_str:8}"
                )

            analysis.extend(
                [
                    "",
                    "🔍 Insights:",
                    f"• Longest thread: {max(message_counts)} messages",
                    f"• Most participants: {max(row[2] for row in results)} people",
                    f"• Threads analyzed: {len(results)}",
                ]
            )

            return "\n".join(analysis)

        except Exception as e:
            return f"Error analyzing thread patterns: {str(e)}"

    def _analyze_communication_network(self, min_emails: int = 5) -> str:
        """Analyze your communication network and relationships."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            query = f"""
            SELECT 
                sender->>'$.email' as contact_email,
                sender->>'$.name' as contact_name,
                COUNT(*) as total_emails,
                COUNT(CASE WHEN is_outgoing = 0 THEN 1 END) as received_from,
                COUNT(CASE WHEN is_outgoing = 1 THEN 1 END) as sent_to,
                COUNT(DISTINCT thread_id) as unique_threads,
                MIN(timestamp) as first_contact,
                MAX(timestamp) as last_contact
            FROM messages
            WHERE sender->>'$.email' IS NOT NULL
              AND sender->>'$.email' != ''
            GROUP BY sender->>'$.email', sender->>'$.name'
            HAVING total_emails >= {min_emails}
            ORDER BY total_emails DESC
            LIMIT 30
            """

            cursor.execute(query)
            results = cursor.fetchall()
            conn.close()

            if not results:
                return f"No contacts found with at least {min_emails} emails."

            # Calculate relationship metrics
            total_contacts = len(results)
            total_interactions = sum(row[2] for row in results)

            analysis = [
                "🌐 Communication Network Analysis",
                f"Total active contacts: {total_contacts}",
                f"Total interactions: {total_interactions}",
                "",
                "Contact | Total | Recv | Sent | Threads | Relationship",
                "-" * 60,
            ]

            for row in results[:15]:
                email, name, total, received, sent, threads, first, last = row

                # Calculate relationship type
                if sent > received * 2:
                    relationship = "You reach out"
                elif received > sent * 2:
                    relationship = "They reach out"
                else:
                    relationship = "Balanced"

                display_name = name if name and name != email else email
                analysis.append(
                    f"{display_name[:20]:20} | {total:5d} | {received:4d} | {sent:4d} | {threads:7d} | {relationship}"
                )

            # Add insights
            top_contact = results[0]
            analysis.extend(
                [
                    "",
                    "🔍 Insights:",
                    f"• Top contact: {top_contact[1] or top_contact[0]} ({top_contact[2]} emails)",
                    f"• Average emails per contact: {total_interactions / total_contacts:.1f}",
                    f"• Total unique relationships: {total_contacts}",
                ]
            )

            return "\n".join(analysis)

        except Exception as e:
            return f"Error analyzing communication network: {str(e)}"
