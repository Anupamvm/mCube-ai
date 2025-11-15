"""
Management command to generate trading signals from Trendlyne data
"""

from django.core.management.base import BaseCommand
from apps.data.signals import SignalGenerator
from apps.data.models import TLStockData


class Command(BaseCommand):
    help = 'Generate trading signals from Trendlyne data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--symbol',
            type=str,
            help='Specific stock symbol to analyze'
        )
        parser.add_argument(
            '--min-confidence',
            type=float,
            default=60.0,
            help='Minimum confidence threshold (default: 60)'
        )
        parser.add_argument(
            '--trade-type',
            type=str,
            choices=['futures', 'options', 'both'],
            default='both',
            help='Type of signals to generate'
        )
        parser.add_argument(
            '--expiry',
            type=str,
            default='CURRENT_MONTH',
            help='Contract expiry (default: CURRENT_MONTH)'
        )

    def handle(self, *args, **options):
        generator = SignalGenerator()
        symbol = options.get('symbol')
        min_confidence = options['min_confidence']
        trade_type = options['trade_type']
        expiry = options['expiry']

        self.stdout.write(self.style.SUCCESS('Generating trading signals...'))

        if symbol:
            # Generate signal for specific symbol
            self.stdout.write(f"\nAnalyzing {symbol}...")

            if trade_type in ['futures', 'both']:
                signal = generator.generate_futures_signal(symbol, expiry)
                self._print_signal(signal)

            if trade_type in ['options', 'both']:
                signal = generator.generate_options_signal(symbol, expiry)
                self._print_signal(signal)

        else:
            # Scan all opportunities
            self.stdout.write(f"\nScanning for opportunities (min confidence: {min_confidence})...")
            opportunities = generator.scan_for_opportunities(min_confidence=min_confidence)

            if not opportunities:
                self.stdout.write(self.style.WARNING(
                    f"No opportunities found with confidence >= {min_confidence}"
                ))
                return

            self.stdout.write(self.style.SUCCESS(
                f"\nFound {len(opportunities)} opportunities:\n"
            ))

            for i, signal in enumerate(opportunities, 1):
                self.stdout.write(f"\n{i}. {signal.symbol}")
                self._print_signal(signal)

    def _print_signal(self, signal):
        """Print formatted signal"""
        # Color code based on signal strength
        if signal.signal.value >= 4:
            style = self.style.SUCCESS
        elif signal.signal.value >= 3:
            style = self.style.HTTP_INFO
        elif signal.signal.value <= 1:
            style = self.style.ERROR
        else:
            style = self.style.WARNING

        self.stdout.write(style(f"\n  Signal: {signal.signal.name}"))
        self.stdout.write(f"  Confidence: {signal.confidence:.1f}%")
        self.stdout.write(f"  Action: {signal.recommended_action}")
        self.stdout.write(f"  Trade Type: {signal.trade_type}")

        self.stdout.write("\n  Reasons:")
        for reason in signal.reasons:
            self.stdout.write(f"    - {reason}")

        if signal.metrics:
            self.stdout.write("\n  Key Metrics:")
            if 'trendlyne_scores' in signal.metrics:
                scores = signal.metrics['trendlyne_scores']
                self.stdout.write(f"    Durability: {scores.get('durability', 0):.1f}")
                self.stdout.write(f"    Valuation: {scores.get('valuation', 0):.1f}")
                self.stdout.write(f"    Momentum: {scores.get('momentum', 0):.1f}")

            if 'oi_buildup' in signal.metrics:
                oi = signal.metrics['oi_buildup']
                self.stdout.write(f"    OI Buildup: {oi.get('buildup_type', 'N/A')}")

            if 'pcr' in signal.metrics:
                pcr = signal.metrics['pcr']
                self.stdout.write(f"    PCR (OI): {pcr.get('pcr_oi', 0):.2f}")
