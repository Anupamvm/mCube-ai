"""
Task Logger Utility

Comprehensive logging utility for Celery background tasks that logs to both:
1. Console (stdout) - for real-time monitoring
2. Database (BkLog model) - for historical analysis and debugging

Usage:
    from apps.core.utils.task_logger import TaskLogger

    # In your Celery task
    @shared_task
    def my_task():
        logger = TaskLogger(
            task_name='my_task',
            task_category='data',
            task_id=my_task.request.id
        )

        logger.start("Starting my task")

        try:
            # Your task logic here
            result = do_something()

            logger.info("Processing complete", context={'count': result.count})
            logger.success("Task completed successfully")

        except Exception as e:
            logger.error("Task failed", error=e)
            raise
"""

import logging
import time
import traceback
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

from django.utils import timezone


class TaskLogger:
    """
    Comprehensive logger for background tasks

    Provides dual logging to console and database with rich context information.
    """

    def __init__(self, task_name: str, task_category: str = 'other',
                 task_id: str = '', enable_console: bool = True,
                 enable_db: bool = True):
        """
        Initialize TaskLogger

        Args:
            task_name: Name of the Celery task
            task_category: Category (data, strategy, position, risk, analytics)
            task_id: Celery task ID for correlation
            enable_console: Whether to log to console
            enable_db: Whether to log to database
        """
        self.task_name = task_name
        self.task_category = task_category
        self.task_id = task_id
        self.enable_console = enable_console
        self.enable_db = enable_db

        # Console logger
        self.console_logger = logging.getLogger(f"celery.task.{task_name}")

        # Track execution time
        self.start_time = None
        self.step_timers = {}

        # Track task status
        self.errors_count = 0
        self.warnings_count = 0

    def _format_console_message(self, level: str, action: str, message: str,
                                 context: Optional[Dict[str, Any]] = None) -> str:
        """Format message for console output"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Level emoji
        level_emoji = {
            'debug': '🔍',
            'info': 'ℹ️',
            'warning': '⚠️',
            'error': '❌',
            'critical': '🚨',
            'success': '✅'
        }
        emoji = level_emoji.get(level, 'ℹ️')

        # Base message
        msg = f"[{timestamp}] {emoji} [{self.task_category.upper()}] {self.task_name}.{action}: {message}"

        # Add context if provided
        if context:
            context_str = ", ".join([f"{k}={v}" for k, v in context.items()])
            msg += f" | {context_str}"

        return msg

    def _log_to_console(self, level: str, message: str):
        """Log to console"""
        if not self.enable_console:
            return

        if level == 'debug':
            self.console_logger.debug(message)
        elif level == 'info' or level == 'success':
            self.console_logger.info(message)
        elif level == 'warning':
            self.console_logger.warning(message)
        elif level == 'error':
            self.console_logger.error(message)
        elif level == 'critical':
            self.console_logger.critical(message)
        else:
            self.console_logger.info(message)

    def _log_to_db(self, level: str, action: str, message: str,
                   execution_time_ms: Optional[int] = None,
                   context_data: Optional[Dict[str, Any]] = None,
                   error_details: str = '',
                   success: bool = True):
        """Log to database"""
        if not self.enable_db:
            return

        try:
            from apps.core.models import BkLog

            # Convert Decimal values to float for JSON serialization
            if context_data:
                cleaned_context = {}
                for key, value in context_data.items():
                    if isinstance(value, Decimal):
                        cleaned_context[key] = float(value)
                    elif isinstance(value, datetime):
                        cleaned_context[key] = value.isoformat()
                    else:
                        cleaned_context[key] = value
            else:
                cleaned_context = {}

            BkLog.log(
                level=level,
                action=action,
                message=message,
                background_task=self.task_name,
                task_category=self.task_category,
                task_id=self.task_id,
                execution_time_ms=execution_time_ms,
                context_data=cleaned_context,
                error_details=error_details,
                success=success
            )
        except Exception as e:
            # Fallback to console logging if DB logging fails
            self.console_logger.error(f"Failed to log to database: {e}")

    def start(self, message: str = "Task started", context: Optional[Dict[str, Any]] = None):
        """Mark task start"""
        self.start_time = time.time()

        console_msg = self._format_console_message('info', 'START', message, context)
        self._log_to_console('info', console_msg)

        self._log_to_db(
            level='info',
            action='START',
            message=message,
            context_data=context
        )

    def step(self, step_name: str, message: str, context: Optional[Dict[str, Any]] = None):
        """Log a step in the task execution"""
        self.step_timers[step_name] = time.time()

        console_msg = self._format_console_message('info', step_name, message, context)
        self._log_to_console('info', console_msg)

        self._log_to_db(
            level='info',
            action=step_name,
            message=message,
            context_data=context
        )

    def debug(self, action: str, message: str, context: Optional[Dict[str, Any]] = None):
        """Log debug message"""
        console_msg = self._format_console_message('debug', action, message, context)
        self._log_to_console('debug', console_msg)

        self._log_to_db(
            level='debug',
            action=action,
            message=message,
            context_data=context
        )

    def info(self, action: str, message: str, context: Optional[Dict[str, Any]] = None):
        """Log info message"""
        console_msg = self._format_console_message('info', action, message, context)
        self._log_to_console('info', console_msg)

        self._log_to_db(
            level='info',
            action=action,
            message=message,
            context_data=context
        )

    def warning(self, action: str, message: str, context: Optional[Dict[str, Any]] = None):
        """Log warning message"""
        self.warnings_count += 1

        console_msg = self._format_console_message('warning', action, message, context)
        self._log_to_console('warning', console_msg)

        self._log_to_db(
            level='warning',
            action=action,
            message=message,
            context_data=context
        )

    def error(self, action: str, message: str, error: Optional[Exception] = None,
              context: Optional[Dict[str, Any]] = None):
        """Log error message"""
        self.errors_count += 1

        # Get error details if exception provided
        error_details = ''
        if error:
            error_details = f"{type(error).__name__}: {str(error)}\n{traceback.format_exc()}"
            message = f"{message} | Error: {str(error)}"

        console_msg = self._format_console_message('error', action, message, context)
        self._log_to_console('error', console_msg)

        if error_details:
            self._log_to_console('error', f"Traceback:\n{error_details}")

        self._log_to_db(
            level='error',
            action=action,
            message=message,
            context_data=context,
            error_details=error_details,
            success=False
        )

    def critical(self, action: str, message: str, error: Optional[Exception] = None,
                 context: Optional[Dict[str, Any]] = None):
        """Log critical error message"""
        self.errors_count += 1

        # Get error details if exception provided
        error_details = ''
        if error:
            error_details = f"{type(error).__name__}: {str(error)}\n{traceback.format_exc()}"
            message = f"{message} | Error: {str(error)}"

        console_msg = self._format_console_message('critical', action, message, context)
        self._log_to_console('critical', console_msg)

        if error_details:
            self._log_to_console('critical', f"Traceback:\n{error_details}")

        self._log_to_db(
            level='critical',
            action=action,
            message=message,
            context_data=context,
            error_details=error_details,
            success=False
        )

    def success(self, message: str = "Task completed successfully",
                context: Optional[Dict[str, Any]] = None):
        """Mark task successful completion"""
        execution_time_ms = None
        if self.start_time:
            execution_time_ms = int((time.time() - self.start_time) * 1000)

        # Add execution metrics to context
        if context is None:
            context = {}

        context.update({
            'execution_time_ms': execution_time_ms,
            'errors_count': self.errors_count,
            'warnings_count': self.warnings_count
        })

        console_msg = self._format_console_message('success', 'COMPLETE', message, context)
        self._log_to_console('success', console_msg)

        self._log_to_db(
            level='info',
            action='COMPLETE',
            message=message,
            execution_time_ms=execution_time_ms,
            context_data=context,
            success=True
        )

    def failure(self, message: str = "Task failed", error: Optional[Exception] = None,
                context: Optional[Dict[str, Any]] = None):
        """Mark task failure"""
        execution_time_ms = None
        if self.start_time:
            execution_time_ms = int((time.time() - self.start_time) * 1000)

        # Get error details if exception provided
        error_details = ''
        if error:
            error_details = f"{type(error).__name__}: {str(error)}\n{traceback.format_exc()}"
            message = f"{message} | Error: {str(error)}"

        # Add execution metrics to context
        if context is None:
            context = {}

        context.update({
            'execution_time_ms': execution_time_ms,
            'errors_count': self.errors_count,
            'warnings_count': self.warnings_count
        })

        console_msg = self._format_console_message('error', 'FAILED', message, context)
        self._log_to_console('error', console_msg)

        if error_details:
            self._log_to_console('error', f"Traceback:\n{error_details}")

        self._log_to_db(
            level='error',
            action='FAILED',
            message=message,
            execution_time_ms=execution_time_ms,
            context_data=context,
            error_details=error_details,
            success=False
        )

    def get_execution_time(self) -> Optional[int]:
        """Get current execution time in milliseconds"""
        if self.start_time:
            return int((time.time() - self.start_time) * 1000)
        return None

    def get_step_time(self, step_name: str) -> Optional[int]:
        """Get time elapsed since a step started (in milliseconds)"""
        if step_name in self.step_timers:
            return int((time.time() - self.step_timers[step_name]) * 1000)
        return None
