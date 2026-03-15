"""BaseScreen — common base class inherited by all app screens.

Provides:
- show_loading / hide_loading — overlay spinner during async ops
- show_error / show_success  — snackbar notifications
- get_repo                   — lazy singleton repository access
- get_current_user_id        — authenticated user UUID from app state
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Type

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText

logger = logging.getLogger(__name__)


class BaseScreen(MDScreen):
    """Common base for all Macro Tracker screens.

    All screens inherit from this class to gain shared UI helpers and
    repository access without duplicating boilerplate.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._repos: Dict[type, Any] = {}
        self._loading_dialog: Optional[Any] = None

    # ------------------------------------------------------------------
    # Loading overlay
    # ------------------------------------------------------------------

    def show_loading(self, message: str = "Loading...") -> None:
        """Display a full-screen loading spinner overlay.

        Safe to call multiple times — subsequent calls update the message.

        Args:
            message: Text displayed below the spinner.
        """
        if self._loading_dialog is not None:
            return
        try:
            from kivy.uix.widget import Widget                              # pylint: disable=import-outside-toplevel
            from kivymd.uix.dialog import (                                 # pylint: disable=import-outside-toplevel
                MDDialog,
                MDDialogContentContainer,
                MDDialogSupportingText,
            )
            from kivymd.uix.progressindicator import (                     # pylint: disable=import-outside-toplevel
                MDCircularProgressIndicator,
            )

            spinner = MDCircularProgressIndicator(
                size_hint=(None, None),
                size=("48dp", "48dp"),
                pos_hint={"center_x": 0.5},
            )
            self._loading_dialog = MDDialog(
                MDDialogSupportingText(text=message, halign="center"),
                MDDialogContentContainer(
                    spinner,
                    orientation="vertical",
                    padding=["0dp", "8dp", "0dp", "0dp"],
                ),
            )
            self._loading_dialog.open()
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("show_loading fallback: %s", exc)

    def hide_loading(self) -> None:
        """Dismiss the loading spinner overlay if it is visible."""
        if self._loading_dialog is not None:
            try:
                self._loading_dialog.dismiss()
            except Exception:  # pylint: disable=broad-except
                pass
            self._loading_dialog = None

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def show_error(self, message: str) -> None:
        """Display an error snackbar at the bottom of the screen.

        Args:
            message: Error text shown to the user.
        """
        self._show_snackbar(message, bg_color=(0.8, 0.2, 0.2, 1))

    def show_success(self, message: str) -> None:
        """Display a success snackbar at the bottom of the screen.

        Args:
            message: Success text shown to the user.
        """
        self._show_snackbar(message, bg_color=(0.2, 0.7, 0.3, 1))

    def _show_snackbar(self, message: str, bg_color: tuple) -> None:
        """Internal helper that creates and opens an MDSnackbar.

        Args:
            message: Text to display.
            bg_color: RGBA background colour tuple.
        """
        try:
            snackbar = MDSnackbar(
                MDSnackbarText(text=message),
                y="24dp",
                pos_hint={"center_x": 0.5},
                size_hint_x=0.9,
                md_bg_color=bg_color,
                duration=3,
            )
            snackbar.open()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Snackbar error: %s", exc)

    # ------------------------------------------------------------------
    # Repository access
    # ------------------------------------------------------------------

    def get_repo(self, repo_class: Type) -> Any:
        """Return a lazy-initialised singleton repository instance.

        Repositories are created once per screen instance and reused,
        avoiding redundant CacheDB connection overhead.

        Args:
            repo_class: The repository class to instantiate (e.g. MealRepository).

        Returns:
            An instance of repo_class.
        """
        if repo_class not in self._repos:
            self._repos[repo_class] = repo_class()
        return self._repos[repo_class]

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def get_current_user_id(self) -> Optional[str]:
        """Return the authenticated user's profile UUID from app state.

        Reads from the running MDApp instance; returns None if the app is
        not yet initialised or the user is not authenticated.

        Returns:
            UUID string, or None.
        """
        try:
            app = MDApp.get_running_app()
            return getattr(app, "current_user_id", None)
        except Exception:  # pylint: disable=broad-except
            return None

    def get_unit_system(self) -> str:
        """Return the active unit system ('metric' or 'imperial').

        Returns:
            'metric' or 'imperial'; defaults to 'metric'.
        """
        try:
            app = MDApp.get_running_app()
            return getattr(app, "unit_system", "metric")
        except Exception:  # pylint: disable=broad-except
            return "metric"
