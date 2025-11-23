"""
URL configuration for LLM app
"""

from django.urls import path
from . import views
from . import test_views

app_name = 'llm'

urlpatterns = [
    # Dashboard
    path('', views.llm_dashboard, name='dashboard'),

    # Chat Interface
    path('chat/', views.chat_interface, name='chat'),

    # News Articles
    path('news/', views.news_list, name='news_list'),
    path('news/<int:article_id>/', views.news_detail, name='news_detail'),

    # Investor Calls
    path('calls/', views.investor_calls_list, name='investor_calls_list'),
    path('calls/<int:call_id>/', views.investor_call_detail, name='investor_call_detail'),

    # Knowledge Base
    path('search/', views.knowledge_base_search, name='knowledge_search'),

    # API Endpoints
    path('api/analyze/', views.analyze_document, name='analyze_document'),
    path('api/ask/', views.ask_question, name='ask_question'),

    # Test Triggers
    path('test/connection/', test_views.trigger_vllm_connection_test, name='test_connection'),
    path('test/generation/', test_views.trigger_text_generation_test, name='test_generation'),
    path('test/sentiment/', test_views.trigger_sentiment_test, name='test_sentiment'),
    path('test/summarization/', test_views.trigger_summarization_test, name='test_summarization'),
    path('test/insights/', test_views.trigger_insight_extraction_test, name='test_insights'),
    path('test/rag/', test_views.trigger_rag_test, name='test_rag'),
    path('test/performance/', test_views.trigger_performance_test, name='test_performance'),
    path('test/all/', test_views.trigger_all_llm_tests, name='test_all'),
]
