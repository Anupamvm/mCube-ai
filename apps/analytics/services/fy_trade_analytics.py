"""
Financial Year Trade Analytics Service

Fetches historical trade data from broker APIs for the current Indian Financial Year
and calculates monthly P&L performance for Futures and Options separately.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from django.db import models, transaction
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncMonth
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_financial_year_dates() -> Tuple[date, date]:
    """
    Get the start and end dates of current Indian financial year.
    FY runs from April 1 to March 31.
    """
    today = date.today()
    if today.month >= 4:
        fy_start = date(today.year, 4, 1)
        fy_end = date(today.year + 1, 3, 31)
    else:
        fy_start = date(today.year - 1, 4, 1)
        fy_end = date(today.year, 3, 31)

    # Don't go beyond today
    fy_end = min(fy_end, today)

    return fy_start, fy_end


def get_fy_label() -> str:
    """Get FY label like 'FY 2024-25'."""
    fy_start, _ = get_financial_year_dates()
    return f"FY {fy_start.year}-{str(fy_start.year + 1)[-2:]}"


class FYTradeAnalytics:
    """
    Service to fetch and analyze FY trade data from broker APIs.
    """

    def __init__(self):
        self.fy_start, self.fy_end = get_financial_year_dates()

    def get_monthly_performance(self, account=None, broker: str = None) -> Dict:
        """
        Calculate monthly P&L performance for FY using CSV imported data.
        Separates Futures and Options.

        Uses BrokerContractPnL (CSV imports) which has accurate P&L per contract.
        Monthly breakdown is based on contract expiry date.

        Args:
            account: Optional account filter
            broker: Optional broker filter ('KOTAK' or 'ICICI')

        Returns:
            dict with monthly breakdown for futures and options
        """
        from apps.brokers.models import BrokerContractPnL

        # Query CSV imported contracts for FY (by expiry date)
        queryset = BrokerContractPnL.objects.filter(
            models.Q(expiry_date__gte=self.fy_start, expiry_date__lte=self.fy_end) |
            models.Q(expiry_date__isnull=True)
        )

        # Apply broker filter if provided
        if broker:
            queryset = queryset.filter(broker=broker)

        # Initialize result structure
        result = {
            'fy_label': get_fy_label(),
            'fy_start': self.fy_start.strftime('%Y-%m-%d'),
            'fy_end': self.fy_end.strftime('%Y-%m-%d'),
            'total_trades': queryset.count(),
            'data_source': 'csv_import',
            'months': [],
            'futures': {
                'total_trades': 0,
                'realized_pnl': Decimal('0'),
                'open_positions': 0,
            },
            'options': {
                'total_trades': 0,
                'realized_pnl': Decimal('0'),
                'open_positions': 0,
            },
            'overall': {
                'total_trades': 0,
                'realized_pnl': Decimal('0'),
                'open_positions': 0,
            }
        }

        if queryset.count() == 0:
            return result

        # Track monthly P&L by expiry month
        monthly_pnl = defaultdict(lambda: {
            'futures': {'pnl': Decimal('0'), 'contracts': 0},
            'options': {'pnl': Decimal('0'), 'contracts': 0},
        })

        for contract in queryset:
            # Use expiry_date for monthly grouping, or created_at if no expiry
            if contract.expiry_date:
                month_key = contract.expiry_date.strftime('%Y-%m')
            else:
                month_key = contract.created_at.strftime('%Y-%m')

            # Determine category from segment
            category = 'options' if contract.segment == 'OPTIONS' else 'futures'

            # Use net_pnl from CSV import (already includes all charges)
            pnl = contract.net_pnl or Decimal('0')

            monthly_pnl[month_key][category]['pnl'] += pnl
            monthly_pnl[month_key][category]['contracts'] += 1

        # Build monthly results
        for month_key in sorted(monthly_pnl.keys()):
            data = monthly_pnl[month_key]

            futures_pnl = data['futures']['pnl']
            options_pnl = data['options']['pnl']
            total_pnl = futures_pnl + options_pnl

            month_entry = {
                'month': month_key,
                'month_label': datetime.strptime(month_key, '%Y-%m').strftime('%b %Y'),
                'futures': {
                    'trades': data['futures']['contracts'],
                    'realized_pnl': float(futures_pnl),
                    'net_pnl': float(futures_pnl),  # Alias for template compatibility
                },
                'options': {
                    'trades': data['options']['contracts'],
                    'realized_pnl': float(options_pnl),
                    'net_pnl': float(options_pnl),  # Alias for template compatibility
                },
                'total': {
                    'trades': data['futures']['contracts'] + data['options']['contracts'],
                    'realized_pnl': float(total_pnl),
                    'net_pnl': float(total_pnl),  # Alias for template compatibility
                }
            }

            result['months'].append(month_entry)

            # Accumulate totals
            result['futures']['total_trades'] += data['futures']['contracts']
            result['futures']['realized_pnl'] += futures_pnl

            result['options']['total_trades'] += data['options']['contracts']
            result['options']['realized_pnl'] += options_pnl

        # Calculate overall totals
        result['overall']['total_trades'] = result['futures']['total_trades'] + result['options']['total_trades']
        result['overall']['realized_pnl'] = result['futures']['realized_pnl'] + result['options']['realized_pnl']

        # Convert Decimals to floats for JSON
        for key in ['futures', 'options', 'overall']:
            result[key]['realized_pnl'] = float(result[key]['realized_pnl'])

        # Backwards compatibility - keep 'net_pnl' as alias for 'realized_pnl'
        for key in ['futures', 'options', 'overall']:
            result[key]['net_pnl'] = result[key]['realized_pnl']

        return result

    def get_broker_breakdown(self, broker: str = None) -> Dict:
        """
        Get performance breakdown by broker using CSV imported data.

        Uses BrokerContractPnL (CSV imports) which has accurate P&L per contract.

        Args:
            broker: Optional broker filter ('KOTAK' or 'ICICI')
        """
        from apps.brokers.models import BrokerContractPnL

        # Query CSV imported contracts for FY (by expiry date)
        queryset = BrokerContractPnL.objects.filter(
            models.Q(expiry_date__gte=self.fy_start, expiry_date__lte=self.fy_end) |
            models.Q(expiry_date__isnull=True)
        )

        # Apply broker filter if provided
        if broker:
            queryset = queryset.filter(broker=broker)

        result = {
            'fy_label': get_fy_label(),
            'data_source': 'csv_import',
            'brokers': []
        }

        broker_names = {'KOTAK': 'Kotak Neo', 'ICICI': 'ICICI Breeze'}

        for broker_code in ['KOTAK', 'ICICI']:
            broker_contracts = queryset.filter(broker=broker_code)

            if not broker_contracts.exists():
                continue

            # Aggregate P&L from CSV imports
            futures_pnl = Decimal('0')
            options_pnl = Decimal('0')
            total_contracts = 0

            for contract in broker_contracts:
                pnl = contract.net_pnl or Decimal('0')
                total_contracts += 1

                if contract.segment == 'OPTIONS':
                    options_pnl += pnl
                else:
                    futures_pnl += pnl

            total_pnl = futures_pnl + options_pnl

            result['brokers'].append({
                'broker': broker_names.get(broker_code, broker_code),
                'broker_code': broker_code,
                'total_trades': total_contracts,
                'net_pnl': float(total_pnl),
                'futures_pnl': float(futures_pnl),
                'options_pnl': float(options_pnl),
                'open_positions': 0,  # CSV imports are closed positions
            })

        return result

    def get_imported_contract_pnl_summary(self, broker: str = None) -> Dict:
        """
        Get FY P&L summary from imported CSV data (BrokerContractPnL).

        This aggregates P&L from CSV imports separately from API-synced trades.
        Useful for historical data that can't be fetched via API.

        Args:
            broker: Optional filter by broker ('KOTAK' or 'ICICI')

        Returns:
            dict with aggregated P&L by segment and broker
        """
        from apps.brokers.models import BrokerContractPnL
        from django.db.models import Sum, Count

        queryset = BrokerContractPnL.objects.all()

        if broker:
            queryset = queryset.filter(broker=broker)

        # Filter by expiry date within FY (for contracts that have expiry)
        # Note: Some imports may not have expiry_date, include those too
        queryset = queryset.filter(
            models.Q(expiry_date__gte=self.fy_start, expiry_date__lte=self.fy_end) |
            models.Q(expiry_date__isnull=True)
        )

        result = {
            'fy_label': get_fy_label(),
            'source': 'CSV Import',
            'total_records': queryset.count(),
            'futures': {
                'records': 0,
                'net_pnl': Decimal('0'),
                'gross_pnl': Decimal('0'),
                'total_charges': Decimal('0'),
            },
            'options': {
                'records': 0,
                'net_pnl': Decimal('0'),
                'gross_pnl': Decimal('0'),
                'total_charges': Decimal('0'),
            },
            'overall': {
                'net_pnl': Decimal('0'),
                'gross_pnl': Decimal('0'),
                'total_charges': Decimal('0'),
            },
            'by_broker': [],
        }

        if queryset.count() == 0:
            return result

        # Aggregate by segment
        segment_agg = queryset.values('segment').annotate(
            records=Count('id'),
            total_net_pnl=Sum('net_pnl'),
            total_gross_pnl=Sum('gross_pnl'),
            total_charges=Sum('total_charges'),
        )

        for agg in segment_agg:
            segment = agg['segment'].lower()
            if segment in result:
                result[segment]['records'] = agg['records']
                result[segment]['net_pnl'] = agg['total_net_pnl'] or Decimal('0')
                result[segment]['gross_pnl'] = agg['total_gross_pnl'] or Decimal('0')
                result[segment]['total_charges'] = agg['total_charges'] or Decimal('0')

        # Calculate overall totals
        result['overall']['net_pnl'] = result['futures']['net_pnl'] + result['options']['net_pnl']
        result['overall']['gross_pnl'] = result['futures']['gross_pnl'] + result['options']['gross_pnl']
        result['overall']['total_charges'] = result['futures']['total_charges'] + result['options']['total_charges']

        # Aggregate by broker
        broker_agg = queryset.values('broker').annotate(
            records=Count('id'),
            total_net_pnl=Sum('net_pnl'),
            futures_pnl=Sum('net_pnl', filter=models.Q(segment='FUTURES')),
            options_pnl=Sum('net_pnl', filter=models.Q(segment='OPTIONS')),
        )

        broker_names = {'KOTAK': 'Kotak Neo', 'ICICI': 'ICICI Breeze'}
        for agg in broker_agg:
            result['by_broker'].append({
                'broker': broker_names.get(agg['broker'], agg['broker']),
                'broker_code': agg['broker'],
                'records': agg['records'],
                'net_pnl': float(agg['total_net_pnl'] or 0),
                'futures_pnl': float(agg['futures_pnl'] or 0),
                'options_pnl': float(agg['options_pnl'] or 0),
            })

        # Convert Decimals to floats for JSON
        for key in ['futures', 'options', 'overall']:
            for field in ['net_pnl', 'gross_pnl', 'total_charges']:
                result[key][field] = float(result[key][field])

        return result

    def get_combined_fy_summary(self) -> Dict:
        """
        Get FY P&L summary from CSV imports (primary data source).

        CSV imports contain accurate P&L data from broker statements.
        API-synced trades are not reliable for historical P&L calculation.

        Returns:
            dict with FY totals from CSV imports
        """
        # Get CSV imported data (now the primary source)
        imported_data = self.get_imported_contract_pnl_summary()

        result = {
            'fy_label': get_fy_label(),
            'data_source': 'csv_import',
            'csv_imports': {
                'total_records': imported_data.get('total_records', 0),
                'futures_pnl': imported_data.get('futures', {}).get('net_pnl', 0),
                'options_pnl': imported_data.get('options', {}).get('net_pnl', 0),
                'total_pnl': imported_data.get('overall', {}).get('net_pnl', 0),
                'total_charges': imported_data.get('overall', {}).get('total_charges', 0),
            },
            'by_broker': imported_data.get('by_broker', []),
            # For backwards compatibility
            'combined': {
                'futures_pnl': imported_data.get('futures', {}).get('net_pnl', 0),
                'options_pnl': imported_data.get('options', {}).get('net_pnl', 0),
                'total_pnl': imported_data.get('overall', {}).get('net_pnl', 0),
            },
        }

        return result


# Singleton
_analytics = None


def get_fy_analytics() -> FYTradeAnalytics:
    """Get singleton FYTradeAnalytics instance."""
    global _analytics
    if _analytics is None:
        _analytics = FYTradeAnalytics()
    return _analytics
