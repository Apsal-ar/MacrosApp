"""Central configuration: Supabase credentials, app constants, feature flags."""

# ---------------------------------------------------------------------------
# Supabase — replace with your project's values before first run
# ---------------------------------------------------------------------------
SUPABASE_URL: str = "https://ykimcuibarkrvnqihyke.supabase.co"
SUPABASE_ANON_KEY: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlraW1jdWliYXJrcnZucWloeWtlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM1NzI1NzgsImV4cCI6MjA4OTE0ODU3OH0.Tw9Se9XE1JnOoby7mqCmp02NBVLR1l4HV0D83WO3IBU"

# ---------------------------------------------------------------------------
# Open Food Facts
# ---------------------------------------------------------------------------
OFF_USER_AGENT: str = "MacroTracker/1.0 (contact@example.com)"
OFF_SEARCH_MAX_RESULTS: int = 20
OFF_MIN_LOCAL_RESULTS: int = 5           # fall back to OFF when local hits < this

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------
ENABLE_BARCODE_SCAN: bool = True         # set False on simulator builds

# ---------------------------------------------------------------------------
# Development: auto-login (set DEV_AUTO_LOGIN = False before shipping)
# ---------------------------------------------------------------------------
DEV_AUTO_LOGIN: bool = True
DEV_AUTO_LOGIN_EMAIL: str = "kat.hodiak@gmail.com"
DEV_AUTO_LOGIN_PASSWORD: str = "MacrosPassword"        # fill in your Supabase password

# ---------------------------------------------------------------------------
# App metadata
# ---------------------------------------------------------------------------
APP_NAME: str = "Macro Tracker"
APP_VERSION: str = "1.0.0"
