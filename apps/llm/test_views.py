"""
Individual LLM test views for triggering tests via UI
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
import time


@login_required
@require_http_methods(["POST"])
def trigger_vllm_connection_test(request):
    """Test vLLM connection"""
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if client.is_enabled():
            return JsonResponse({
                'success': True,
                'status': 'pass',
                'message': f'Connected to {client.base_url} | Model: {client.model[:50]}...',
                'details': {
                    'base_url': client.base_url,
                    'model': client.model,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'status': 'fail',
                'message': f'Cannot connect to {client.base_url}',
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })


@login_required
@require_http_methods(["POST"])
def trigger_text_generation_test(request):
    """Test text generation"""
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if not client.is_enabled():
            return JsonResponse({
                'success': False,
                'status': 'skip',
                'message': 'vLLM not connected',
            })

        success, response, metadata = client.generate(
            prompt="What is 2+2? Answer with just the number.",
            temperature=0.1,
            max_tokens=10
        )

        if success:
            tokens = metadata.get('usage', {}).get('total_tokens', 0)
            time_ms = metadata.get('processing_time_ms', 0)
            return JsonResponse({
                'success': True,
                'status': 'pass',
                'message': f'Response: "{response[:50]}..." | {tokens} tokens in {time_ms}ms',
                'details': {
                    'response': response,
                    'tokens': tokens,
                    'time_ms': time_ms,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'status': 'fail',
                'message': f'Generation failed: {metadata.get("error", "Unknown error")}',
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })


@login_required
@require_http_methods(["POST"])
def trigger_sentiment_test(request):
    """Test sentiment analysis"""
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if not client.is_enabled():
            return JsonResponse({
                'success': False,
                'status': 'skip',
                'message': 'vLLM not connected',
            })

        test_text = "The stock market rallied today with strong gains across all sectors."
        success, sentiment, metadata = client.analyze_sentiment(test_text)

        if success and sentiment:
            label = sentiment.get('label', 'N/A')
            score = sentiment.get('score', 0)
            confidence = sentiment.get('confidence', 0)
            return JsonResponse({
                'success': True,
                'status': 'pass',
                'message': f'Label: {label} | Score: {score:.2f} | Confidence: {confidence:.2f}',
                'details': sentiment,
            })
        else:
            return JsonResponse({
                'success': False,
                'status': 'fail',
                'message': f'Analysis failed: {metadata.get("error", "Unknown error")}',
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })


@login_required
@require_http_methods(["POST"])
def trigger_summarization_test(request):
    """Test text summarization"""
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if not client.is_enabled():
            return JsonResponse({
                'success': False,
                'status': 'skip',
                'message': 'vLLM not connected',
            })

        test_text = """RELIANCE Industries reported strong Q4 results with revenue growth of 15% YoY.
        The company added multiple new contracts worth over $500M. Management expressed confidence
        in maintaining growth momentum in the upcoming fiscal year."""

        success, summary, metadata = client.summarize(test_text, max_length=30)

        if success and summary:
            word_count = len(summary.split())
            return JsonResponse({
                'success': True,
                'status': 'pass',
                'message': f'Summary generated ({word_count} words): "{summary[:60]}..."',
                'details': {
                    'summary': summary,
                    'word_count': word_count,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'status': 'fail',
                'message': f'Summarization failed: {metadata.get("error", "Unknown error")}',
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })


@login_required
@require_http_methods(["POST"])
def trigger_insight_extraction_test(request):
    """Test insight extraction"""
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if not client.is_enabled():
            return JsonResponse({
                'success': False,
                'status': 'skip',
                'message': 'vLLM not connected',
            })

        test_text = """TCS reported revenue growth of 15% YoY. The company added 10 new large deals
        worth over $100M each. Attrition rate decreased to 12% from 18%. Management guided for
        double-digit growth in FY25."""

        success, insights, metadata = client.extract_insights(test_text, num_insights=3)

        if success and insights:
            insight_count = len(insights) if isinstance(insights, list) else 0
            first_insight = insights[0][:50] if insight_count > 0 else "N/A"
            return JsonResponse({
                'success': True,
                'status': 'pass',
                'message': f'Extracted {insight_count} insights | First: "{first_insight}..."',
                'details': {
                    'insights': insights,
                    'count': insight_count,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'status': 'fail',
                'message': f'Extraction failed: {metadata.get("error", "Unknown error")}',
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })


@login_required
@require_http_methods(["POST"])
def trigger_rag_test(request):
    """Test question answering (RAG)"""
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if not client.is_enabled():
            return JsonResponse({
                'success': False,
                'status': 'skip',
                'message': 'vLLM not connected',
            })

        context = "RELIANCE Industries reported Q4 net profit of Rs 19,299 crore, up 12% YoY. The board recommended a dividend of Rs 9 per share."
        question = "What was the net profit?"

        success, answer, metadata = client.answer_question(question, context, temperature=0.1)

        if success and answer:
            return JsonResponse({
                'success': True,
                'status': 'pass',
                'message': f'Answer: "{answer[:70]}..."',
                'details': {
                    'answer': answer,
                    'question': question,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'status': 'fail',
                'message': f'QA failed: {metadata.get("error", "Unknown error")}',
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })


@login_required
@require_http_methods(["POST"])
def trigger_performance_test(request):
    """Test LLM performance"""
    try:
        from apps.llm.services.vllm_client import get_vllm_client
        client = get_vllm_client()

        if not client.is_enabled():
            return JsonResponse({
                'success': False,
                'status': 'skip',
                'message': 'vLLM not connected',
            })

        start = time.time()
        success, _, metadata = client.generate(
            prompt="Say hello",
            temperature=0.1,
            max_tokens=10
        )
        elapsed_ms = int((time.time() - start) * 1000)

        if success:
            status = 'pass' if elapsed_ms < 2000 else 'warning'
            quality = "Good" if elapsed_ms < 1000 else "Acceptable" if elapsed_ms < 2000 else "Slow"
            return JsonResponse({
                'success': True,
                'status': status,
                'message': f'Response time: {elapsed_ms}ms | {quality}',
                'details': {
                    'time_ms': elapsed_ms,
                    'quality': quality,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'status': 'fail',
                'message': 'Performance test failed',
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'status': 'fail',
            'message': f'Error: {str(e)}',
        })


@login_required
@require_http_methods(["POST"])
def trigger_all_llm_tests(request):
    """Run all LLM tests"""
    results = {}

    # Run each test
    tests = [
        ('connection', trigger_vllm_connection_test),
        ('generation', trigger_text_generation_test),
        ('sentiment', trigger_sentiment_test),
        ('summarization', trigger_summarization_test),
        ('insights', trigger_insight_extraction_test),
        ('rag', trigger_rag_test),
        ('performance', trigger_performance_test),
    ]

    for test_name, test_func in tests:
        try:
            result = test_func(request)
            results[test_name] = result.content.decode('utf-8')
        except Exception as e:
            results[test_name] = {'error': str(e)}

    return JsonResponse({
        'success': True,
        'message': 'All tests completed',
        'results': results,
    })
