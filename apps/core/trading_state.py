"""
Trading State Management

Centralized state management for trading system controls.

This module provides a simple in-memory state for trading controls
like pause/resume. For production, this should be moved to Redis or database.
"""

import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TradingState:
    """
    Singleton class to manage trading system state
    """

    _instance = None
    _state = {
        'trading_paused': False,
        'paused_at': None,
        'paused_by': None,
        'pause_reason': None,
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TradingState, cls).__new__(cls)
        return cls._instance

    def is_trading_paused(self) -> bool:
        """Check if trading is currently paused"""
        return self._state['trading_paused']

    def pause_trading(self, reason: str = "Manual pause via bot", paused_by: str = "TELEGRAM_BOT"):
        """
        Pause automated trading

        Args:
            reason: Reason for pausing
            paused_by: Who/what paused trading
        """
        if self._state['trading_paused']:
            logger.warning("Trading is already paused")
            return

        self._state['trading_paused'] = True
        self._state['paused_at'] = datetime.now()
        self._state['paused_by'] = paused_by
        self._state['pause_reason'] = reason

        logger.warning(
            f"Trading PAUSED by {paused_by}: {reason}"
        )

    def resume_trading(self):
        """Resume automated trading"""
        if not self._state['trading_paused']:
            logger.warning("Trading is not paused")
            return

        logger.info(
            f"Trading RESUMED (was paused by {self._state['paused_by']} "
            f"at {self._state['paused_at']})"
        )

        self._state['trading_paused'] = False
        self._state['paused_at'] = None
        self._state['paused_by'] = None
        self._state['pause_reason'] = None

    def get_state(self) -> Dict:
        """Get current trading state"""
        return self._state.copy()


# Global instance
_trading_state = TradingState()


def is_trading_paused() -> bool:
    """
    Check if trading is paused

    Returns:
        bool: True if trading is paused
    """
    return _trading_state.is_trading_paused()


def pause_trading(reason: str = "Manual pause", paused_by: str = "SYSTEM"):
    """
    Pause automated trading

    Args:
        reason: Reason for pausing
        paused_by: Who/what paused trading
    """
    _trading_state.pause_trading(reason, paused_by)


def resume_trading():
    """Resume automated trading"""
    _trading_state.resume_trading()


def get_trading_state() -> Dict:
    """
    Get current trading state

    Returns:
        dict: Current state dictionary
    """
    return _trading_state.get_state()
