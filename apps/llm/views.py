"""
LLM views for mCube Trading System

This module contains views for LLM-related functionality including:
- Document management (upload, view, list)
- LLM chat interface
- Document analysis
- Knowledge base search
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Q
from django.core.paginator import Paginator
import json
import logging

from apps.data.models import NewsArticle, InvestorCall, KnowledgeBase
from apps.llm.services.vllm_client import get_vllm_client

logger = logging.getLogger(__name__)


@login_required
def llm_dashboard(request):
    """
    LLM Dashboard - Overview of documents and LLM capabilities
    """
    context = {}

    try:
        # Get document counts
        news_count = NewsArticle.objects.count()
        calls_count = InvestorCall.objects.count()
        kb_count = KnowledgeBase.objects.count()

        # Get recent processed documents
        recent_news = NewsArticle.objects.filter(processed=True).order_by('-processed_at')[:5]
        recent_calls = InvestorCall.objects.filter(processed=True).order_by('-processed_at')[:5]

        # Get LLM stats
        vllm_client = get_vllm_client()
        llm_enabled = vllm_client.is_enabled()

        context.update({
            'news_count': news_count,
            'calls_count': calls_count,
            'kb_count': kb_count,
            'recent_news': recent_news,
            'recent_calls': recent_calls,
            'llm_enabled': llm_enabled,
            'llm_model': vllm_client.model if llm_enabled else 'N/A',
        })

    except Exception as e:
        logger.error(f"Error fetching LLM dashboard data: {e}")
        context['error'] = str(e)

    return render(request, 'llm/dashboard.html', context)


@login_required
def chat_interface(request):
    """
    Interactive chat interface with LLM
    """
    context = {}

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            messages = data.get('messages', [])
            temperature = float(data.get('temperature', 0.7))
            max_tokens = int(data.get('max_tokens', 1000))

            vllm_client = get_vllm_client()

            if not vllm_client.is_enabled():
                return JsonResponse({
                    'success': False,
                    'error': 'vLLM client is not enabled'
                })

            success, response, metadata = vllm_client.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            return JsonResponse({
                'success': success,
                'response': response,
                'metadata': metadata
            })

        except Exception as e:
            logger.error(f"Error in chat interface: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    # GET request - show chat UI
    vllm_client = get_vllm_client()
    context['llm_enabled'] = vllm_client.is_enabled()
    context['llm_model'] = vllm_client.model

    return render(request, 'llm/chat.html', context)


@login_required
def news_list(request):
    """
    List all news articles with search and filter
    """
    # Get filter parameters
    search = request.GET.get('search', '')
    symbol = request.GET.get('symbol', '')
    source = request.GET.get('source', '')
    processed = request.GET.get('processed', '')

    # Build query
    articles = NewsArticle.objects.all()

    if search:
        articles = articles.filter(
            Q(title__icontains=search) |
            Q(content__icontains=search) |
            Q(summary__icontains=search)
        )

    if symbol:
        articles = articles.filter(symbols_mentioned__contains=symbol)

    if source:
        articles = articles.filter(source=source)

    if processed == 'yes':
        articles = articles.filter(processed=True)
    elif processed == 'no':
        articles = articles.filter(processed=False)

    # Pagination
    paginator = Paginator(articles, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get sources for filter
    sources = NewsArticle.objects.values_list('source', flat=True).distinct()

    context = {
        'page_obj': page_obj,
        'search': search,
        'symbol': symbol,
        'source': source,
        'processed': processed,
        'sources': sources,
    }

    return render(request, 'llm/news_list.html', context)


@login_required
def news_detail(request, article_id):
    """
    View detailed news article with LLM analysis
    """
    article = get_object_or_404(NewsArticle, id=article_id)

    context = {
        'article': article,
    }

    return render(request, 'llm/news_detail.html', context)


@login_required
def investor_calls_list(request):
    """
    List all investor calls with search and filter
    """
    # Get filter parameters
    search = request.GET.get('search', '')
    symbol = request.GET.get('symbol', '')
    call_type = request.GET.get('call_type', '')
    processed = request.GET.get('processed', '')

    # Build query
    calls = InvestorCall.objects.all()

    if search:
        calls = calls.filter(
            Q(company__icontains=search) |
            Q(transcript__icontains=search) |
            Q(executive_summary__icontains=search)
        )

    if symbol:
        calls = calls.filter(symbol=symbol)

    if call_type:
        calls = calls.filter(call_type=call_type)

    if processed == 'yes':
        calls = calls.filter(processed=True)
    elif processed == 'no':
        calls = calls.filter(processed=False)

    # Pagination
    paginator = Paginator(calls, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
        'symbol': symbol,
        'call_type': call_type,
        'processed': processed,
        'call_types': InvestorCall._meta.get_field('call_type').choices,
    }

    return render(request, 'llm/investor_calls_list.html', context)


@login_required
def investor_call_detail(request, call_id):
    """
    View detailed investor call with LLM analysis
    """
    call = get_object_or_404(InvestorCall, id=call_id)

    context = {
        'call': call,
    }

    return render(request, 'llm/investor_call_detail.html', context)


@login_required
@require_http_methods(["POST"])
def analyze_document(request):
    """
    Analyze a document (news or investor call) using LLM
    """
    try:
        data = json.loads(request.body)
        doc_type = data.get('doc_type')  # 'news' or 'call'
        doc_id = data.get('doc_id')

        vllm_client = get_vllm_client()

        if not vllm_client.is_enabled():
            return JsonResponse({
                'success': False,
                'error': 'vLLM client is not enabled'
            })

        if doc_type == 'news':
            article = get_object_or_404(NewsArticle, id=doc_id)
            text = f"Title: {article.title}\n\nContent: {article.content}"
        elif doc_type == 'call':
            call = get_object_or_404(InvestorCall, id=doc_id)
            text = f"Company: {call.company}\n\nTranscript: {call.transcript}"
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid document type'
            })

        # Analyze sentiment
        success_sent, sentiment, _ = vllm_client.analyze_sentiment(text)

        # Generate summary
        success_summ, summary, _ = vllm_client.summarize(text, max_length=150)

        # Extract insights
        success_ins, insights, _ = vllm_client.extract_insights(text, num_insights=5)

        # Update the document
        if doc_type == 'news':
            article.sentiment_label = sentiment.get('label') if success_sent else None
            article.sentiment_score = sentiment.get('score') if success_sent else None
            article.sentiment_confidence = sentiment.get('confidence') if success_sent else None
            article.llm_summary = summary if success_summ else ''
            article.key_insights = insights if success_ins else []
            article.processed = True
            article.processed_at = timezone.now()
            article.save()
        elif doc_type == 'call':
            call.management_tone = sentiment.get('label') if success_sent else None
            call.confidence_score = sentiment.get('confidence') if success_sent else None
            call.executive_summary = summary if success_summ else ''
            call.key_highlights = insights if success_ins else []
            call.processed = True
            call.processed_at = timezone.now()
            call.save()

        return JsonResponse({
            'success': True,
            'sentiment': sentiment if success_sent else None,
            'summary': summary if success_summ else None,
            'insights': insights if success_ins else None
        })

    except Exception as e:
        logger.error(f"Error analyzing document: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def knowledge_base_search(request):
    """
    Search knowledge base
    """
    query = request.GET.get('q', '')

    context = {
        'query': query,
        'results': []
    }

    if query:
        # Simple text search for now
        # TODO: Implement vector search with embeddings
        results = KnowledgeBase.objects.filter(
            Q(title__icontains=query) |
            Q(content_chunk__icontains=query)
        )[:20]

        context['results'] = results

    return render(request, 'llm/knowledge_search.html', context)


@login_required
@require_http_methods(["POST"])
def ask_question(request):
    """
    Ask a question using RAG (Retrieval Augmented Generation)
    """
    try:
        data = json.loads(request.body)
        question = data.get('question', '')

        if not question:
            return JsonResponse({
                'success': False,
                'error': 'Question is required'
            })

        # TODO: Implement proper RAG with vector search
        # For now, do simple text search and answer

        vllm_client = get_vllm_client()

        if not vllm_client.is_enabled():
            return JsonResponse({
                'success': False,
                'error': 'vLLM client is not enabled'
            })

        # Find relevant documents
        relevant_docs = KnowledgeBase.objects.filter(
            Q(content_chunk__icontains=question)
        )[:3]

        # Build context from relevant documents
        context = "\n\n".join([doc.content_chunk for doc in relevant_docs])

        if not context:
            context = "No relevant information found in the knowledge base."

        # Ask LLM
        success, answer, metadata = vllm_client.answer_question(
            question=question,
            context=context
        )

        return JsonResponse({
            'success': success,
            'answer': answer,
            'sources': [
                {
                    'title': doc.title,
                    'source_type': doc.source_type
                }
                for doc in relevant_docs
            ],
            'metadata': metadata
        })

    except Exception as e:
        logger.error(f"Error asking question: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })