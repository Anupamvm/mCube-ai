"""
Management command to validate a trade setup
"""

from django.core.management.base import BaseCommand
from apps.data.validators import TradeValidator


class Command(BaseCommand):
    help = 'Validate a trade setup using Trendlyne data'

    def add_arguments(self, parser):
        parser.add_argument('symbol', type=str, help='Stock symbol')
        parser.add_argument('trade_type', type=str,
                          choices=['FUTURES_LONG', 'FUTURES_SHORT', 'CALL_BUY', 'PUT_BUY'],
                          help='Type of trade')
        parser.add_argument('--expiry', type=str, default='CURRENT_MONTH',
                          help='Contract expiry')
        parser.add_argument('--strike', type=float, help='Option strike price')

    def handle(self, *args, **options):
        validator = TradeValidator()

        symbol = options['symbol']
        trade_type = options['trade_type']
        expiry = options.get('expiry')
        strike = options.get('strike')

        self.stdout.write(self.style.SUCCESS(
            f"\nValidating {trade_type} on {symbol}...\n"
        ))

        # Validate
        result = validator.validate_trade(trade_type, symbol, expiry, strike)

        # Print results
        if result.approved:
            self.stdout.write(self.style.SUCCESS(
                f"✅ TRADE APPROVED (Confidence: {result.confidence:.1f}%)\n"
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f"❌ TRADE REJECTED (Confidence: {result.confidence:.1f}%)\n"
            ))

        # Print reasons
        if result.reasons:
            self.stdout.write(self.style.SUCCESS("Positive Factors:"))
            for reason in result.reasons:
                self.stdout.write(f"  {reason}")

        # Print warnings
        if result.warnings:
            self.stdout.write(self.style.WARNING("\nWarnings:"))
            for warning in result.warnings:
                self.stdout.write(f"  {warning}")

        # Print metrics
        if result.metrics:
            self.stdout.write("\nDetailed Metrics:")

            if 'trendlyne_scores' in result.metrics:
                scores = result.metrics['trendlyne_scores']
                self.stdout.write(f"\n  Trendlyne Scores:")
                self.stdout.write(f"    Durability: {scores.get('durability', 0):.1f}/100")
                self.stdout.write(f"    Valuation: {scores.get('valuation', 0):.1f}/100")
                self.stdout.write(f"    Momentum: {scores.get('momentum', 0):.1f}/100")
                self.stdout.write(f"    Overall Rating: {scores.get('overall_rating', 'N/A')}")

            if 'oi_buildup' in result.metrics:
                oi = result.metrics['oi_buildup']
                self.stdout.write(f"\n  OI Analysis:")
                self.stdout.write(f"    Buildup Type: {oi.get('buildup_type', 'N/A')}")
                self.stdout.write(f"    Sentiment: {oi.get('sentiment', 'N/A')}")
                self.stdout.write(f"    Price Change: {oi.get('price_change_pct', 0):.2f}%")
                self.stdout.write(f"    OI Change: {oi.get('oi_change_pct', 0):.2f}%")

            if 'dma' in result.metrics:
                dma = result.metrics['dma']
                self.stdout.write(f"\n  DMA Analysis:")
                self.stdout.write(f"    Trend: {dma.get('trend', 'N/A')}")
                self.stdout.write(f"    Above DMAs: {dma.get('above_dma_count', 0)}/{dma.get('total_dmas', 0)}")
                if dma.get('golden_cross'):
                    self.stdout.write(f"    Golden Cross: Yes")
                if dma.get('death_cross'):
                    self.stdout.write(f"    Death Cross: Yes")

            if 'rsi' in result.metrics:
                rsi = result.metrics['rsi']
                self.stdout.write(f"\n  RSI:")
                self.stdout.write(f"    Value: {rsi.get('rsi', 0):.1f}")
                self.stdout.write(f"    Condition: {rsi.get('condition', 'N/A')}")

        self.stdout.write("")
