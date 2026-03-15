"""Macro Tracker — application entry point.

Responsibilities:
- Initialise Supabase client
- Build the SQLite cache schema (CacheDB singleton)
- Construct the ScreenManager with all four screens
- Authenticate the user (email + password via Supabase Auth)
- Start the SyncManager polling loop post-login
- Expose app-level state: current_user_id, unit_system
"""

from __future__ import annotations

import logging
import os
from typing import Optional

# Kivy must be configured before any other kivy imports
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.clock import Clock                                    # noqa: E402
from kivy.core.window import Window                             # noqa: E402
from kivy.lang import Builder                                   # noqa: E402
from kivy.uix.screenmanager import ScreenManager, SlideTransition  # noqa: E402
from kivymd.app import MDApp                                    # noqa: E402
from kivymd.uix.screen import MDScreen                          # noqa: E402
from kivymd.uix.boxlayout import MDBoxLayout                   # noqa: E402

import config                                                   # noqa: E402
from sync.cache_db import CacheDB                               # noqa: E402
from sync.sync_manager import SyncManager                       # noqa: E402
from screens.profile_screen import ProfileScreen                # noqa: E402
from screens.goals_screen import GoalsScreen                    # noqa: E402
from screens.tracker_screen import TrackerScreen                # noqa: E402
from screens.settings_screen import SettingsScreen              # noqa: E402
from widgets.macro_pie_chart import MacroPieChart               # noqa: E402
from widgets.macro_progress_bar import MacroProgressBar         # noqa: E402
from widgets.meal_card import MealCard                          # noqa: E402
from widgets.food_item_row import FoodItemRow                   # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# Simulate iPhone SE screen on desktop
Window.size = (390, 844)

# ---------------------------------------------------------------------------
# Login screen (inline KV)
# ---------------------------------------------------------------------------

Builder.load_string("""
<LoginScreen>:
    MDBoxLayout:
        orientation: "vertical"
        padding: ["24dp", "60dp", "24dp", "40dp"]
        spacing: "20dp"

        MDLabel:
            text: "Macro Tracker"
            font_style: "Display"
            role: "small"
            halign: "center"
            size_hint_y: None
            height: "80dp"

        MDLabel:
            text: "Track your nutrition, reach your goals"
            font_style: "Body"
            role: "medium"
            halign: "center"
            theme_text_color: "Secondary"
            size_hint_y: None
            height: "36dp"

        Widget:
            size_hint_y: 0.1

        MDTextField:
            id: email_field
            hint_text: "Email"
            input_type: "mail"

        MDTextField:
            id: password_field
            hint_text: "Password"
            password: True

        MDLabel:
            id: error_label
            text: ""
            theme_text_color: "Error"
            size_hint_y: None
            height: "24dp"
            halign: "center"

        MDButton:
            style: "filled"
            size_hint_x: 1
            height: "52dp"
            on_release: app.login(root.ids.email_field.text, root.ids.password_field.text, root)

            MDButtonText:
                text: "Sign In"

        MDButton:
            style: "text"
            size_hint_x: 1
            on_release: app.sign_up(root.ids.email_field.text, root.ids.password_field.text, root)

            MDButtonText:
                text: "Create Account"

        Widget:
            size_hint_y: 1
""")


class LoginScreen(MDScreen):
    """Email/password login and sign-up screen."""
    name = "login"


# ---------------------------------------------------------------------------
# Bottom navigation shell
# ---------------------------------------------------------------------------

Builder.load_string("""
<AppShell>:
    MDBoxLayout:
        orientation: "vertical"

        ScreenManager:
            id: inner_sm
            TrackerScreen:
            ProfileScreen:
            GoalsScreen:
            SettingsScreen:

        MDNavigationBar:
            id: nav_bar
            on_switch_tabs: app.switch_tab(args[1], args[2], args[3])

            MDNavigationItem:
                MDNavigationItemIcon:
                    icon: "food-apple"
                MDNavigationItemLabel:
                    text: "Tracker"

            MDNavigationItem:
                MDNavigationItemIcon:
                    icon: "account"
                MDNavigationItemLabel:
                    text: "Profile"

            MDNavigationItem:
                MDNavigationItemIcon:
                    icon: "target"
                MDNavigationItemLabel:
                    text: "Goals"

            MDNavigationItem:
                MDNavigationItemIcon:
                    icon: "cog"
                MDNavigationItemLabel:
                    text: "Settings"
""")


class AppShell(MDScreen):
    """Outer shell screen containing the bottom navigation + inner ScreenManager."""
    name = "app"


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class MacroTrackerApp(MDApp):
    """Root Kivy application.

    App-level state:
        current_user_id (str): Authenticated user's profile UUID.
        unit_system (str): 'metric' | 'imperial', shared across all screens.
        version (str): Display version string.
    """

    current_user_id: str = ""
    unit_system: str = "metric"
    version: str = config.APP_VERSION

    # Screen name → inner ScreenManager name mapping
    _TAB_SCREENS = ["tracker", "profile", "goals", "settings"]

    def build(self) -> ScreenManager:
        """Build and return the root ScreenManager.

        Returns:
            A ScreenManager containing the login and app shell screens.
        """
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.theme_style = "Light"

        # Initialise SQLite cache (creates schema if not exists)
        CacheDB.get_instance()

        # Initialise Supabase client
        self._supabase = self._init_supabase()

        root_sm = ScreenManager(transition=SlideTransition())
        root_sm.add_widget(LoginScreen())
        root_sm.add_widget(AppShell())

        if config.DEV_AUTO_LOGIN:
            root_sm.current = "app"

        return root_sm

    def on_start(self) -> None:
        """Kivy lifecycle hook — auto-login for development when configured."""
        if config.DEV_AUTO_LOGIN:
            Clock.schedule_once(self._auto_login, 0.3)

    def _auto_login(self, _dt: float) -> None:
        """Perform a silent Supabase login without showing the login screen.

        Falls back to offline-demo mode when no password is configured.
        """
        if self._supabase is not None and config.DEV_AUTO_LOGIN_PASSWORD:
            try:
                response = self._supabase.auth.sign_in_with_password(
                    {
                        "email": config.DEV_AUTO_LOGIN_EMAIL,
                        "password": config.DEV_AUTO_LOGIN_PASSWORD,
                    }
                )
                logger.info("Auto-login succeeded for %s", config.DEV_AUTO_LOGIN_EMAIL)
                self._on_auth_success(response.user.id)
                return
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Auto-login failed: %s — falling back to offline demo", exc)

        # No password configured or Supabase unavailable → offline demo.
        # Use uuid5 (deterministic, derived from the email) so the same
        # profile row is found in SQLite on every subsequent restart.
        import uuid  # pylint: disable=import-outside-toplevel
        demo_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"offline:{config.DEV_AUTO_LOGIN_EMAIL}"))
        logger.info("Auto-login: offline demo mode, id=%s", demo_id)
        self._on_auth_success(demo_id)

    def _init_supabase(self):
        """Create and return the Supabase client.

        Returns:
            supabase.Client instance, or None if credentials are placeholder values.
        """
        if "YOUR_PROJECT_ID" in config.SUPABASE_URL:
            logger.warning(
                "Supabase credentials not configured — running in offline-only mode. "
                "Set SUPABASE_URL and SUPABASE_ANON_KEY in config.py"
            )
            return None
        try:
            from supabase import create_client  # pylint: disable=import-outside-toplevel
            return create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Supabase init failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self, email: str, password: str, login_screen: LoginScreen) -> None:
        """Attempt Supabase email/password sign-in.

        Args:
            email: User's email address.
            password: User's password.
            login_screen: The LoginScreen widget (used to show error messages).
        """
        if not email or not password:
            login_screen.ids.error_label.text = "Please enter email and password"
            return

        if self._supabase is None:
            self._enter_offline_demo(login_screen)
            return

        try:
            response = self._supabase.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
            user_id = response.user.id
            self._on_auth_success(user_id, login_screen)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Login failed: %s", exc)
            login_screen.ids.error_label.text = "Sign in failed. Check your credentials."

    def sign_up(self, email: str, password: str, login_screen: LoginScreen) -> None:
        """Register a new user via Supabase Auth.

        Args:
            email: New user's email address.
            password: New user's password (min 6 chars enforced by Supabase).
            login_screen: The LoginScreen widget.
        """
        if not email or not password:
            login_screen.ids.error_label.text = "Please enter email and password"
            return

        if self._supabase is None:
            login_screen.ids.error_label.text = "Offline mode — cannot create accounts"
            return

        try:
            response = self._supabase.auth.sign_up({"email": email, "password": password})
            user_id = response.user.id
            self._on_auth_success(user_id, login_screen)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Sign-up failed: %s", exc)
            login_screen.ids.error_label.text = "Sign up failed. Try a different email."

    def _on_auth_success(
        self,
        user_id: str,
        login_screen: Optional[LoginScreen] = None,
    ) -> None:
        """Called after successful auth — bootstrap profile and start sync.

        Args:
            user_id: Authenticated user's UUID.
            login_screen: The LoginScreen widget, or None when auto-logging in.
        """
        self.current_user_id = user_id
        if login_screen is not None:
            login_screen.ids.error_label.text = ""

        self._ensure_profile_exists(user_id)

        if self._supabase is not None:
            SyncManager.get_instance().start(self._supabase, user_id)

        # Navigate to app shell (no-op if already there)
        self.root.current = "app"

        # Always land on the Profile tab
        try:
            app_shell = self.root.get_screen("app")
            app_shell.ids.inner_sm.current = "profile"
        except Exception:  # pylint: disable=broad-except
            pass

    def _enter_offline_demo(self, login_screen: LoginScreen) -> None:
        """Enter offline demo mode with a deterministic user ID derived from email.

        Using uuid5 ensures the same profile row is found in SQLite across
        restarts, so data entered offline is never silently lost.

        Args:
            login_screen: The LoginScreen (provides the email and is navigated away from).
        """
        import uuid  # pylint: disable=import-outside-toplevel
        email = login_screen.ids.email_field.text.strip() or "anonymous"
        demo_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"offline:{email}"))
        logger.info("Entering offline demo mode, id=%s", demo_id)
        self._on_auth_success(demo_id, login_screen)

    def _ensure_profile_exists(self, user_id: str) -> None:
        """Create a bare profile row in SQLite if one doesn't exist yet.

        Args:
            user_id: The newly authenticated user's UUID.
        """
        from services.repository import ProfileRepository, GoalsRepository, Repository  # noqa: PLC0415
        from models.user import Profile, Goals                                           # noqa: PLC0415
        import time                                                                      # noqa: PLC0415

        profile_repo = ProfileRepository()
        if profile_repo.get(user_id) is None:
            profile_repo.save(Profile(id=user_id, email="", updated_at=time.time()))

        goals_repo = GoalsRepository()
        if goals_repo.get_for_profile(user_id) is None:
            goals_repo.save(Goals(
                id=Repository.new_id(),
                profile_id=user_id,
                updated_at=time.time(),
            ))

    # ------------------------------------------------------------------
    # Bottom tab navigation
    # ------------------------------------------------------------------

    def switch_tab(self, item: object, item_icon: str, item_text: str) -> None:
        """Switch the inner ScreenManager to the tapped tab's screen.

        Args:
            item: The MDNavigationItem that was activated.
            item_icon: Icon name string (unused).
            item_text: Display label of the tab, e.g. 'Tracker'.
        """
        try:
            app_shell = self.root.get_screen("app")
            inner_sm: ScreenManager = app_shell.ids.inner_sm
            screen_name = item_text.lower()
            if screen_name in self._TAB_SCREENS:
                inner_sm.current = screen_name
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Tab switch failed: %s", exc)


if __name__ == "__main__":
    MacroTrackerApp().run()
