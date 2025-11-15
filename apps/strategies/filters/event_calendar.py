"""
Economic Event Calendar Filter

Checks for major economic events that could cause market volatility.

Events to Monitor:
- RBI Monetary Policy announcements
- US Federal Reserve (FOMC) meetings
- Union Budget
- GDP/Inflation data releases
- Major political events (elections)
- Global central bank meetings

Rationale:
Market-neutral strategies like short strangles are vulnerable to volatility spikes.
Major economic events often cause sharp directional moves, increasing gamma risk.
Better to skip trading during event-heavy periods.
"""

import logging
from typing import Dict, List
from datetime import datetime, timedelta

from django.utils import timezone
from django.db.models import Q

from apps.data.models import Event

logger = logging.getLogger(__name__)


def check_economic_events(days_ahead: int = 5) -> Dict:
    """
    Check for major economic events in the next N days

    Args:
        days_ahead: Number of days to look ahead (default: 5)

    Returns:
        dict: {
            'passed': bool,
            'message': str,
            'details': {
                'events_found': int,
                'major_events': list,
                'days_checked': int
            }
        }
    """

    logger.info(f"Checking economic events for next {days_ahead} days...")

    # Date range
    today = timezone.now().date()
    end_date = today + timedelta(days=days_ahead)

    # Query events
    try:
        events = Event.objects.filter(
            event_date__gte=today,
            event_date__lte=end_date,
            is_active=True
        ).order_by('event_date')

        total_events = events.count()

        # Filter for HIGH importance events
        major_events = events.filter(
            Q(importance='HIGH') | Q(importance='CRITICAL')
        )

        major_events_list = []

        for event in major_events:
            days_until = (event.event_date - today).days

            major_events_list.append({
                'title': event.title,
                'date': event.event_date.strftime('%Y-%m-%d'),
                'days_until': days_until,
                'importance': event.importance,
                'description': event.description
            })

            logger.warning(
                f"⚠️ {event.importance} event in {days_until} days: "
                f"{event.title} ({event.event_date})"
            )

        # Decision
        passed = major_events.count() == 0

        if passed:
            message = f"No major events in next {days_ahead} days"
            logger.info(f"✅ {message}")
        else:
            event = major_events.first()
            days_until = (event.event_date - today).days
            message = (
                f"{major_events.count()} major event(s) upcoming: "
                f"{event.title} in {days_until} day(s)"
            )
            logger.warning(f"❌ {message}")

        details = {
            'events_found': total_events,
            'major_events': major_events_list,
            'days_checked': days_ahead
        }

        return {
            'passed': passed,
            'message': message,
            'details': details
        }

    except Exception as e:
        logger.error(f"Error checking economic events: {e}", exc_info=True)

        # On error, fail safely (block trade)
        return {
            'passed': False,
            'message': f"Event calendar check failed: {str(e)}",
            'details': {
                'events_found': 0,
                'major_events': [],
                'days_checked': days_ahead,
                'error': str(e)
            }
        }


def get_upcoming_events(days_ahead: int = 30, importance: str = None) -> List[Dict]:
    """
    Get list of upcoming economic events

    Args:
        days_ahead: Number of days to look ahead
        importance: Filter by importance (None, 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')

    Returns:
        list: List of event dictionaries
    """

    logger.info(f"Fetching upcoming events (next {days_ahead} days)...")

    today = timezone.now().date()
    end_date = today + timedelta(days=days_ahead)

    # Query events
    events_query = Event.objects.filter(
        event_date__gte=today,
        event_date__lte=end_date,
        is_active=True
    )

    # Filter by importance if specified
    if importance:
        events_query = events_query.filter(importance=importance)

    events_query = events_query.order_by('event_date')

    # Format results
    events_list = []

    for event in events_query:
        days_until = (event.event_date - today).days

        events_list.append({
            'title': event.title,
            'description': event.description,
            'date': event.event_date.strftime('%Y-%m-%d'),
            'days_until': days_until,
            'importance': event.importance,
            'category': event.category,
            'impact': event.expected_impact
        })

    logger.info(f"Found {len(events_list)} upcoming events")

    return events_list


def add_event(
    title: str,
    event_date: datetime.date,
    importance: str = 'MEDIUM',
    category: str = 'ECONOMIC',
    description: str = '',
    expected_impact: str = ''
) -> Event:
    """
    Add a new event to the calendar

    Args:
        title: Event title
        event_date: Date of event
        importance: LOW, MEDIUM, HIGH, CRITICAL
        category: ECONOMIC, POLITICAL, CORPORATE, etc.
        description: Detailed description
        expected_impact: Expected market impact

    Returns:
        Event: Created event instance
    """

    logger.info(f"Adding event: {title} on {event_date}")

    event = Event.objects.create(
        title=title,
        description=description,
        event_date=event_date,
        importance=importance,
        category=category,
        expected_impact=expected_impact,
        is_active=True
    )

    logger.info(f"✅ Event added: {event.id} - {event.title}")

    return event


def populate_sample_events():
    """
    Populate sample economic events for testing

    This function creates sample events to test the event calendar filter.
    """

    logger.info("Populating sample economic events...")

    today = timezone.now().date()

    sample_events = [
        {
            'title': 'RBI Monetary Policy Decision',
            'event_date': today + timedelta(days=3),
            'importance': 'HIGH',
            'category': 'MONETARY_POLICY',
            'description': 'Reserve Bank of India to announce repo rate decision',
            'expected_impact': 'High volatility expected around 10:00 AM'
        },
        {
            'title': 'US Federal Reserve FOMC Meeting',
            'event_date': today + timedelta(days=7),
            'importance': 'HIGH',
            'category': 'MONETARY_POLICY',
            'description': 'Federal Reserve interest rate decision',
            'expected_impact': 'Global markets impact, India affected next day'
        },
        {
            'title': 'India GDP Data Release',
            'event_date': today + timedelta(days=10),
            'importance': 'MEDIUM',
            'category': 'ECONOMIC',
            'description': 'Quarterly GDP growth data',
            'expected_impact': 'Moderate market reaction'
        },
        {
            'title': 'Union Budget Announcement',
            'event_date': today + timedelta(days=45),
            'importance': 'CRITICAL',
            'category': 'POLITICAL',
            'description': 'Annual Union Budget presentation',
            'expected_impact': 'Extreme volatility, avoid trading 2 days before and after'
        },
        {
            'title': 'US Non-Farm Payrolls',
            'event_date': today + timedelta(days=2),
            'importance': 'MEDIUM',
            'category': 'ECONOMIC',
            'description': 'US employment data release',
            'expected_impact': 'Minor impact on Indian markets'
        },
    ]

    created_count = 0

    for event_data in sample_events:
        # Check if event already exists
        existing = Event.objects.filter(
            title=event_data['title'],
            event_date=event_data['event_date']
        ).first()

        if not existing:
            Event.objects.create(**event_data, is_active=True)
            created_count += 1
            logger.info(f"  ✅ Created: {event_data['title']} ({event_data['event_date']})")
        else:
            logger.debug(f"  ⏭️  Skipped (exists): {event_data['title']}")

    logger.info(f"✅ Populated {created_count} sample events")

    return created_count
