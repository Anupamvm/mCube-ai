from django.contrib import admin
from .models import (
    MarketData, OptionChain, Event, TLStockData, ContractData, ContractStockData,
    NewsArticle, InvestorCall, KnowledgeBase, AnalystPriceTarget, AnalystReport
)


@admin.register(MarketData)
class MarketDataAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'timestamp', 'close', 'volume', 'open_interest']
    list_filter = ['exchange']
    search_fields = ['symbol']
    date_hierarchy = 'timestamp'


@admin.register(OptionChain)
class OptionChainAdmin(admin.ModelAdmin):
    list_display = ['underlying', 'strike', 'option_type', 'expiry_date', 'ltp', 'oi', 'delta']
    list_filter = ['underlying', 'option_type', 'expiry_date']
    search_fields = ['underlying']


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'event_date', 'importance', 'country']
    list_filter = ['importance', 'country', 'category']
    search_fields = ['title', 'description']
    date_hierarchy = 'event_date'


@admin.register(TLStockData)
class TLStockDataAdmin(admin.ModelAdmin):
    list_display = ['stock_name', 'nsecode', 'current_price', 'market_capitalization',
                    'trendlyne_durability_score', 'trendlyne_valuation_score', 'trendlyne_momentum_score']
    list_filter = ['sector_name', 'industry_name']
    search_fields = ['stock_name', 'nsecode', 'bsecode', 'isin']
    readonly_fields = ['created_at', 'updated_at']

    # No fieldsets - Django will show ALL 172 fields in alphabetical order


@admin.register(ContractData)
class ContractDataAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'option_type', 'strike_price', 'expiry', 'price', 'oi', 'iv', 'delta']
    list_filter = ['symbol', 'option_type', 'expiry']
    search_fields = ['symbol']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ContractStockData)
class ContractStockDataAdmin(admin.ModelAdmin):
    list_display = ['stock_name', 'nse_code', 'current_price', 'fno_pcr_oi', 'fno_pcr_vol',
                    'fno_total_oi', 'annualized_volatility']
    list_filter = ['industry_name']
    search_fields = ['stock_name', 'nse_code']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'source', 'published_at', 'sentiment_label',
                    'market_impact', 'processed', 'embedding_stored']
    list_filter = ['source', 'category', 'sentiment_label', 'market_impact', 'processed']
    search_fields = ['title', 'summary', 'content']
    date_hierarchy = 'published_at'
    readonly_fields = ['created_at', 'updated_at', 'processed_at']

    fieldsets = (
        ('Article Info', {
            'fields': ('title', 'source', 'author', 'published_at', 'url')
        }),
        ('Content', {
            'fields': ('summary', 'content', 'llm_summary')
        }),
        ('Categorization', {
            'fields': ('category', 'tags', 'symbols_mentioned', 'sectors_mentioned', 'key_insights')
        }),
        ('Sentiment Analysis', {
            'fields': ('sentiment_score', 'sentiment_label', 'sentiment_confidence', 'market_impact')
        }),
        ('Processing Status', {
            'fields': ('processed', 'processed_at', 'embedding_stored', 'embedding_id')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(InvestorCall)
class InvestorCallAdmin(admin.ModelAdmin):
    list_display = ['company', 'symbol', 'call_type', 'call_date', 'quarter',
                    'management_tone', 'trading_signal', 'processed']
    list_filter = ['call_type', 'management_tone', 'trading_signal', 'processed']
    search_fields = ['company', 'symbol', 'transcript']
    date_hierarchy = 'call_date'
    readonly_fields = ['created_at', 'updated_at', 'processed_at']

    fieldsets = (
        ('Call Info', {
            'fields': ('company', 'symbol', 'call_type', 'call_date', 'quarter', 'participants')
        }),
        ('Transcript', {
            'fields': ('transcript',)
        }),
        ('LLM Analysis', {
            'fields': ('executive_summary', 'key_highlights', 'financial_metrics',
                      'management_tone', 'outlook', 'concerns_raised')
        }),
        ('Trading Impact', {
            'fields': ('trading_signal', 'confidence_score')
        }),
        ('Processing Status', {
            'fields': ('processed', 'processed_at', 'embedding_stored', 'embedding_id')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ['title', 'source_type', 'chunk_index', 'times_retrieved',
                    'relevance_score', 'embedding_stored']
    list_filter = ['source_type', 'embedding_stored']
    search_fields = ['title', 'content_chunk', 'symbols', 'sectors', 'topics']
    readonly_fields = ['created_at', 'updated_at', 'last_retrieved_at']

    fieldsets = (
        ('Source Info', {
            'fields': ('source_type', 'source_id', 'source_url')
        }),
        ('Content', {
            'fields': ('title', 'content_chunk', 'chunk_index')
        }),
        ('Metadata', {
            'fields': ('metadata', 'symbols', 'sectors', 'topics')
        }),
        ('Embedding', {
            'fields': ('embedding_id', 'embedding_stored')
        }),
        ('Usage Stats', {
            'fields': ('times_retrieved', 'last_retrieved_at', 'relevance_score')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AnalystPriceTarget)
class AnalystPriceTargetAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'stock_name', 'current_price', 'avg_target_price',
                    'upside_pct', 'analyst_count', 'sell_count', 'fetch_timestamp', 'scrape_success']
    list_filter = ['scrape_success']
    search_fields = ['symbol', 'nse_code', 'stock_name']
    readonly_fields = ['created_at', 'updated_at', 'fetch_timestamp']

    fieldsets = (
        ('Stock Info', {
            'fields': ('symbol', 'nse_code', 'trendlyne_id', 'stock_name')
        }),
        ('Price Targets', {
            'fields': ('current_price', 'avg_target_price', 'upside_pct', 'analyst_count')
        }),
        ('Recommendations', {
            'fields': ('strong_buy_count', 'buy_count', 'hold_count', 'sell_count', 'strong_sell_count')
        }),
        ('Metadata', {
            'fields': ('source_url', 'scrape_success', 'scrape_error', 'fetch_timestamp')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AnalystReport)
class AnalystReportAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'author', 'report_date', 'recommendation_type',
                    'target_price', 'upside_pct', 'sentiment_score', 'llm_processed']
    list_filter = ['recommendation_type', 'trade_recommendation', 'llm_processed', 'pdf_download_success']
    search_fields = ['symbol', 'nse_code', 'author', 'report_title', 'llm_summary']
    date_hierarchy = 'report_date'
    readonly_fields = ['created_at', 'updated_at', 'llm_processed_at']

    fieldsets = (
        ('Stock Info', {
            'fields': ('symbol', 'nse_code', 'trendlyne_id')
        }),
        ('Report Metadata', {
            'fields': ('report_date', 'author', 'report_title', 'recommendation_type')
        }),
        ('Price Data', {
            'fields': ('ltp_at_report', 'target_price', 'upside_pct')
        }),
        ('PDF Content', {
            'fields': ('pdf_url', 'pdf_local_path', 'pdf_content_text', 'pdf_download_success')
        }),
        ('LLM Analysis', {
            'fields': ('llm_summary', 'key_insights', 'sentiment_score',
                      'trade_recommendation', 'risk_factors', 'catalysts')
        }),
        ('Processing Status', {
            'fields': ('llm_processed', 'llm_processed_at', 'processing_error')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
