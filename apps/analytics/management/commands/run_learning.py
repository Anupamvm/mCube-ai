"""
Management command to run the learning analysis manually.

Usage:
    python manage.py run_learning              # Create session and run full analysis
    python manage.py run_learning --analyze    # Only analyze trades
    python manage.py run_learning --patterns   # Only discover patterns
    python manage.py run_learning --suggest    # Only generate suggestions
    python manage.py run_learning --status     # Show current status
"""

from django.core.management.base import BaseCommand

from apps.analytics.models import (
    LearningSession,
    TradePerformance,
    LearningPattern,
    ParameterAdjustment,
)
from apps.analytics.services.learning_engine import LearningEngine
from apps.positions.models import Position


class Command(BaseCommand):
    help = 'Run learning analysis to generate suggestions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--analyze',
            action='store_true',
            help='Only analyze trades (create TradePerformance records)',
        )
        parser.add_argument(
            '--patterns',
            action='store_true',
            help='Only discover patterns (create LearningPattern records)',
        )
        parser.add_argument(
            '--suggest',
            action='store_true',
            help='Only generate suggestions (create ParameterAdjustment records)',
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show current database status',
        )
        parser.add_argument(
            '--session-name',
            type=str,
            default='Manual Learning Session',
            help='Name for the learning session',
        )

    def handle(self, *args, **options):
        if options['status']:
            self.show_status()
            return

        # Get or create a running session
        session = LearningSession.objects.filter(status='RUNNING').first()

        if not session:
            self.stdout.write(self.style.WARNING('No active session found. Creating new one...'))
            engine = LearningEngine(min_trades=1)  # Lower threshold for testing
            session = engine.start_learning(options['session_name'])
            self.stdout.write(self.style.SUCCESS(f'Created session: {session.name}'))
        else:
            self.stdout.write(f'Using existing session: {session.name}')

        engine = LearningEngine(min_trades=1)

        # Determine what to run
        run_all = not (options['analyze'] or options['patterns'] or options['suggest'])

        # Step 1: Analyze trades
        if run_all or options['analyze']:
            self.stdout.write('\n--- Step 1: Analyzing Trades ---')
            closed_positions = Position.objects.filter(status='CLOSED').count()
            self.stdout.write(f'Closed positions: {closed_positions}')

            if closed_positions == 0:
                self.stdout.write(self.style.WARNING('No closed positions to analyze.'))
            else:
                trades_analyzed = engine.analyze_trades(session)
                self.stdout.write(self.style.SUCCESS(f'Analyzed {trades_analyzed} trades'))

        # Step 2: Discover patterns
        if run_all or options['patterns']:
            self.stdout.write('\n--- Step 2: Discovering Patterns ---')
            trade_perfs = TradePerformance.objects.count()
            self.stdout.write(f'Trade performance records: {trade_perfs}')

            if trade_perfs == 0:
                self.stdout.write(self.style.WARNING('No trade performances to analyze for patterns.'))
            else:
                patterns_found = engine.discover_patterns(session)
                self.stdout.write(self.style.SUCCESS(f'Discovered {patterns_found} patterns'))

        # Step 3: Generate suggestions
        if run_all or options['suggest']:
            self.stdout.write('\n--- Step 3: Generating Suggestions ---')
            patterns = LearningPattern.objects.filter(session=session).count()
            self.stdout.write(f'Patterns available: {patterns}')

            suggestions_count = engine.suggest_improvements(session)
            self.stdout.write(self.style.SUCCESS(f'Generated {suggestions_count} suggestions'))

        # Show final status
        self.stdout.write('\n')
        self.show_status()

    def show_status(self):
        self.stdout.write(self.style.HTTP_INFO('=== LEARNING SYSTEM STATUS ==='))

        # Positions
        total_positions = Position.objects.count()
        closed_positions = Position.objects.filter(status='CLOSED').count()
        self.stdout.write(f'Positions: {total_positions} total, {closed_positions} closed')

        # Sessions
        sessions = LearningSession.objects.count()
        running = LearningSession.objects.filter(status='RUNNING').count()
        self.stdout.write(f'Learning Sessions: {sessions} total, {running} running')

        # Trade Performances
        performances = TradePerformance.objects.count()
        self.stdout.write(f'Trade Performances: {performances}')

        # Patterns
        patterns = LearningPattern.objects.count()
        actionable = LearningPattern.objects.filter(is_actionable=True).count()
        self.stdout.write(f'Learning Patterns: {patterns} total, {actionable} actionable')

        # Suggestions
        suggestions = ParameterAdjustment.objects.count()
        suggested = ParameterAdjustment.objects.filter(status='SUGGESTED').count()
        approved = ParameterAdjustment.objects.filter(status='APPROVED').count()
        self.stdout.write(f'Parameter Adjustments: {suggestions} total')
        self.stdout.write(f'  - SUGGESTED: {suggested}')
        self.stdout.write(f'  - APPROVED: {approved}')

        # Show recent suggestions
        if suggested > 0:
            self.stdout.write('\n--- Recent Suggestions ---')
            for s in ParameterAdjustment.objects.filter(status='SUGGESTED')[:5]:
                self.stdout.write(f'  {s.parameter_name}: {s.current_value} -> {s.suggested_value} ({s.confidence}% confidence)')
