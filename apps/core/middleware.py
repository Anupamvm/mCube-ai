"""
Custom middleware for mCube Trading System

This module contains middleware for enhanced error handling and logging.
"""

import logging
import traceback
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.conf import settings
from django.template import TemplateDoesNotExist, TemplateSyntaxError

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware:
    """
    Middleware to catch and handle errors gracefully.
    Provides better error messages and logging.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        """
        Handle exceptions that occur during request processing.
        Gracefully handles template errors, database errors, and other exceptions.
        """
        # Log the exception with full traceback
        logger.error(
            f"Exception occurred: {exception}\n"
            f"Path: {request.path}\n"
            f"Method: {request.method}\n"
            f"User: {request.user if hasattr(request, 'user') else 'Anonymous'}\n"
            f"IP: {self.get_client_ip(request)}\n"
            f"Traceback:\n{traceback.format_exc()}"
        )

        # For AJAX/API requests, return JSON error
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
           request.path.startswith('/api/'):
            return JsonResponse({
                'error': True,
                'message': str(exception) if settings.DEBUG else 'An error occurred',
                'type': exception.__class__.__name__,
                'path': request.path,
            }, status=500)

        # Handle template errors gracefully
        if isinstance(exception, (TemplateDoesNotExist, TemplateSyntaxError)):
            return self._render_fallback_error(
                request,
                '500',
                'Template Error',
                f'A template error occurred: {exception}' if settings.DEBUG else 'An error occurred while rendering the page.',
                str(exception) if settings.DEBUG else None
            )

        # For regular requests, return None to let Django's default handler work
        # This will trigger the handler500 error view
        return None

    def _render_fallback_error(self, request, code, title, message, details=None):
        """
        Render a fallback error page when templates fail.
        Uses inline HTML to avoid template dependencies.
        """
        html = f'''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{code} - {title} | mCube Trading System</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                }}
                .error-container {{
                    background: white;
                    border-radius: 12px;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                    max-width: 600px;
                    width: 100%;
                    padding: 40px;
                    text-align: center;
                }}
                .error-code {{
                    font-size: 72px;
                    font-weight: 700;
                    color: #667eea;
                    margin-bottom: 10px;
                }}
                h1 {{
                    font-size: 28px;
                    font-weight: 600;
                    color: #333;
                    margin-bottom: 15px;
                }}
                p {{
                    font-size: 16px;
                    color: #666;
                    margin-bottom: 20px;
                    line-height: 1.6;
                }}
                .details {{
                    background: #f8f9fa;
                    padding: 15px;
                    border-radius: 6px;
                    border-left: 4px solid #dc3545;
                    margin-bottom: 30px;
                    text-align: left;
                    font-family: monospace;
                    font-size: 13px;
                    color: #721c24;
                    overflow-x: auto;
                }}
                .btn {{
                    display: inline-block;
                    padding: 12px 30px;
                    margin: 5px;
                    border-radius: 6px;
                    text-decoration: none;
                    font-weight: 500;
                    background: #667eea;
                    color: white;
                    transition: all 0.3s ease;
                }}
                .btn:hover {{
                    background: #5568d3;
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
                }}
            </style>
        </head>
        <body>
            <div class="error-container">
                <div class="error-code">{code}</div>
                <h1>{title}</h1>
                <p>{message}</p>
                {'<div class="details">' + details + '</div>' if details else ''}
                <a href="/" class="btn">Go to Home</a>
                <a href="javascript:history.back()" class="btn">Go Back</a>
            </div>
        </body>
        </html>
        '''
        return HttpResponse(html, status=int(code))

    @staticmethod
    def get_client_ip(request):
        """Get the client's IP address from the request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class URLLoggingMiddleware:
    """
    Middleware to log all incoming requests.
    Useful for debugging URL routing issues.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Log request details
        if settings.DEBUG:
            logger.debug(
                f"Request: {request.method} {request.path} "
                f"| User: {request.user if hasattr(request, 'user') else 'Anonymous'} "
                f"| IP: {self.get_client_ip(request)}"
            )

        response = self.get_response(request)

        # Log response status
        if settings.DEBUG:
            logger.debug(f"Response: {response.status_code} for {request.path}")

        return response

    @staticmethod
    def get_client_ip(request):
        """Get the client's IP address from the request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SecurityHeadersMiddleware:
    """
    Add security headers to all responses.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Add security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['X-XSS-Protection'] = '1; mode=block'

        # Only add HSTS in production
        if not settings.DEBUG:
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        return response
