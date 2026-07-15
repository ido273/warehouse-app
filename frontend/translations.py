"""UI translation strings for the frontend.

Coverage in this pass: shared chrome (navbar, sidebar, add/edit modals, card
dropdown, delete confirmation) used across every page, plus the standalone
auth pages (login, register, onboarding, workspace-pending). Per-page body
content (item/box card grids, filters, item detail, search, error pages) is
not yet translated — see hebrew_i18n_followup.md for the tracked list.
"""

translations = {
    "en": {
        # ── Navbar / sidebar ──
        "nav_home": "Home",
        "nav_all_items": "All Items",
        "nav_search": "Search",
        "nav_navigation": "Navigation",
        "nav_storage_locations": "Storage Locations",
        "nav_workspace": "Workspace",
        "nav_new_join_workspace": "New / Join Workspace",
        "nav_invite_code": "Invite Code",
        "nav_admin": "Admin",
        "nav_manage_locations": "Manage Locations",
        "nav_pending_requests": "Pending Requests",
        "nav_settings": "Settings",
        "nav_export": "Export",
        "nav_export_csv": "Export CSV",
        "nav_export_excel": "Export Excel",
        "nav_account": "Account",
        "nav_sign_out": "Sign Out",
        "quick_search_placeholder": "Quick search…",

        # ── Add modal ──
        "add_new": "Add New",
        "tab_box": "Box",
        "tab_item": "Item",
        "box_name_label": "Box Name *",
        "box_name_placeholder": "e.g. Electronics Box",
        "location_label": "Location",
        "no_location": "No location",
        "new_location_placeholder": "New location name…",
        "visibility_label": "Visibility",
        "private": "🔒 Private",
        "public": "🌐 Public",
        "image_label": "Image",
        "optional": "(optional)",
        "click_to_upload": "Click to upload a photo",
        "create_box_btn": "Create Box",
        "item_name_label": "Item Name *",
        "item_name_placeholder": "e.g. USB Cable",
        "category_label": "Category",
        "category_placeholder": "e.g. Electronics",
        "quantity_label": "Quantity",
        "box_label": "Box",
        "no_box_option": "— No Box —",
        "inherited_from_box": "Inherited from box",
        "tags_label": "Tags",
        "tags_hint": "(press Enter to add)",
        "tag_placeholder": "e.g. cable…",
        "generate_tags_btn": "Generate Tags",
        "generating_tags": "Generating tags…",
        "no_suggestions_found": "No suggestions found",
        "create_item_btn": "Create Item",
        "skip_btn": "Skip",
        "item_added": "Item added!",
        "add_another_question": "Add another item to this box?",
        "add_another_btn": "Add Another",
        "done_btn": "Done",

        # ── Edit modal ──
        "edit_title": "Edit",
        "save_changes_btn": "Save Changes",
        "replace_image_label": "Replace Image",

        # ── Card dropdown ──
        "edit_action": "Edit",
        "delete_action": "Delete",
        "options_title": "Options",

        # ── Common / toasts ──
        "network_error": "Network error",
        "box_name_required": "Box name is required",
        "item_name_required": "Item name is required",
        "failed_to_create_box": "Failed to create box",
        "failed_to_create_item": "Failed to create item",
        "box_created_msg": "Box created — now add items to it!",
        "enter_item_name_first": "Enter an item name first",
        "failed_to_generate_tags": "Failed to generate tags",
        "update_failed": "Update failed",
        "box_updated": "Box updated!",
        "item_updated": "Item updated!",
        "box_deleted": "Box deleted",
        "item_deleted": "Item deleted",
        "delete_failed": "Delete failed",
        "delete_confirm": 'Delete {type} "{name}"? This cannot be undone.',
        "box_word": "box",
        "item_word": "item",

        # ── Language toggle ──
        "lang_toggle_label": "EN",

        # ── Workspace settings: tag language ──
        "tag_language_label": "Tag Language",
        "tag_language_en_option": "English",
        "tag_language_he_option": "עברית (Hebrew + technical terms in English)",

        # ── Auth: login ──
        "welcome_back": "Welcome back",
        "sign_in_sub": "Sign in to your account to continue",
        "account_created_msg": "Account created! You can now sign in.",
        "email_label": "Email",
        "password_label": "Password",
        "sign_in_btn": "Sign In",
        "no_account_msg": "Don't have an account?",
        "create_one_link": "Create one",

        # ── Auth: register ──
        "create_account_title": "Create an account",
        "join_warehousems_sub": "Join WarehouseMS to manage your inventory",
        "first_name_label": "First Name",
        "last_name_label": "Last Name",
        "password_hint": "At least 6 characters",
        "create_account_btn": "Create Account",
        "have_account_msg": "Already have an account?",
        "sign_in_link": "Sign in",

        # ── Onboarding ──
        "onboarding_sub": "Every inventory lives in a workspace. Create one or join an existing team.",
        "create_workspace_title": "Create a new workspace",
        "create_workspace_desc": "Start fresh — you'll be the admin",
        "workspace_name_label": "Workspace name",
        "workspace_name_placeholder": "e.g. Main Warehouse",
        "create_workspace_btn": "Create Workspace",
        "or_join_existing": "or join an existing one",
        "join_workspace_title": "Join with an invite code",
        "join_workspace_desc": "Ask your team admin for the 8-character code",
        "invite_code_label": "Invite code",
        "join_workspace_btn": "Join Workspace",
        "already_set_up": "Already set up?",
        "go_to_dashboard": "Go to dashboard",

        # ── Workspace pending ──
        "pending_title": "Request pending approval",
        "pending_msg": "Your request to join the workspace has been sent. The workspace admin will review it shortly.",
        "pending_step1": "Request submitted successfully",
        "pending_step2": "Waiting for admin approval",
        "pending_step3": "You'll be added as a viewer once approved",
        "join_different_workspace": "Join a different workspace",
        "sign_out_btn": "Sign out",
    },
    "he": {
        # ── Navbar / sidebar ──
        "nav_home": "בית",
        "nav_all_items": "כל הפריטים",
        "nav_search": "חיפוש",
        "nav_navigation": "ניווט",
        "nav_storage_locations": "מיקומי אחסון",
        "nav_workspace": "סביבת עבודה",
        "nav_new_join_workspace": "חדש / הצטרפות לסביבת עבודה",
        "nav_invite_code": "קוד הזמנה",
        "nav_admin": "ניהול",
        "nav_manage_locations": "ניהול מיקומים",
        "nav_pending_requests": "בקשות ממתינות",
        "nav_settings": "הגדרות",
        "nav_export": "ייצוא",
        "nav_export_csv": "ייצוא CSV",
        "nav_export_excel": "ייצוא Excel",
        "nav_account": "חשבון",
        "nav_sign_out": "התנתקות",
        "quick_search_placeholder": "חיפוש מהיר…",

        # ── Add modal ──
        "add_new": "הוספה חדשה",
        "tab_box": "קופסה",
        "tab_item": "פריט",
        "box_name_label": "שם קופסה *",
        "box_name_placeholder": "למשל קופסת אלקטרוניקה",
        "location_label": "מיקום",
        "no_location": "ללא מיקום",
        "new_location_placeholder": "שם מיקום חדש…",
        "visibility_label": "נראות",
        "private": "🔒 פרטי",
        "public": "🌐 ציבורי",
        "image_label": "תמונה",
        "optional": "(רשות)",
        "click_to_upload": "לחץ להעלאת תמונה",
        "create_box_btn": "צור קופסה",
        "item_name_label": "שם פריט *",
        "item_name_placeholder": "למשל כבל USB",
        "category_label": "קטגוריה",
        "category_placeholder": "למשל אלקטרוניקה",
        "quantity_label": "כמות",
        "box_label": "קופסה",
        "no_box_option": "— ללא קופסה —",
        "inherited_from_box": "בירושה מהקופסה",
        "tags_label": "תגיות",
        "tags_hint": "(הקש Enter להוספה)",
        "tag_placeholder": "למשל כבל…",
        "generate_tags_btn": "צור תגיות",
        "generating_tags": "יוצר תגיות…",
        "no_suggestions_found": "לא נמצאו הצעות",
        "create_item_btn": "צור פריט",
        "skip_btn": "דלג",
        "item_added": "הפריט נוסף!",
        "add_another_question": "להוסיף פריט נוסף לקופסה זו?",
        "add_another_btn": "הוסף עוד",
        "done_btn": "סיום",

        # ── Edit modal ──
        "edit_title": "עריכה",
        "save_changes_btn": "שמור שינויים",
        "replace_image_label": "החלף תמונה",

        # ── Card dropdown ──
        "edit_action": "עריכה",
        "delete_action": "מחיקה",
        "options_title": "אפשרויות",

        # ── Common / toasts ──
        "network_error": "שגיאת רשת",
        "box_name_required": "נדרש שם קופסה",
        "item_name_required": "נדרש שם פריט",
        "failed_to_create_box": "יצירת הקופסה נכשלה",
        "failed_to_create_item": "יצירת הפריט נכשלה",
        "box_created_msg": "הקופסה נוצרה — כעת הוסף אליה פריטים!",
        "enter_item_name_first": "הזן שם פריט תחילה",
        "failed_to_generate_tags": "יצירת התגיות נכשלה",
        "update_failed": "העדכון נכשל",
        "box_updated": "הקופסה עודכנה!",
        "item_updated": "הפריט עודכן!",
        "box_deleted": "הקופסה נמחקה",
        "item_deleted": "הפריט נמחק",
        "delete_failed": "המחיקה נכשלה",
        "delete_confirm": 'למחוק {type} "{name}"? לא ניתן לבטל פעולה זו.',
        "box_word": "קופסה",
        "item_word": "פריט",

        # ── Language toggle ──
        "lang_toggle_label": "עב",

        # ── Workspace settings: tag language ──
        "tag_language_label": "שפת תגים",
        "tag_language_en_option": "אנגלית",
        "tag_language_he_option": "עברית (Hebrew + technical terms in English)",

        # ── Auth: login ──
        "welcome_back": "ברוך שובך",
        "sign_in_sub": "התחבר לחשבונך כדי להמשיך",
        "account_created_msg": "החשבון נוצר! כעת תוכל להתחבר.",
        "email_label": "דוא\"ל",
        "password_label": "סיסמה",
        "sign_in_btn": "התחברות",
        "no_account_msg": "אין לך חשבון?",
        "create_one_link": "צור אחד",

        # ── Auth: register ──
        "create_account_title": "יצירת חשבון",
        "join_warehousems_sub": "הצטרף ל-WarehouseMS כדי לנהל את המלאי שלך",
        "first_name_label": "שם פרטי",
        "last_name_label": "שם משפחה",
        "password_hint": "לפחות 6 תווים",
        "create_account_btn": "צור חשבון",
        "have_account_msg": "כבר יש לך חשבון?",
        "sign_in_link": "התחבר",

        # ── Onboarding ──
        "onboarding_sub": "כל מלאי שייך לסביבת עבודה. צור אחת או הצטרף לצוות קיים.",
        "create_workspace_title": "צור סביבת עבודה חדשה",
        "create_workspace_desc": "התחל מחדש — תהיה המנהל",
        "workspace_name_label": "שם סביבת עבודה",
        "workspace_name_placeholder": "למשל מחסן ראשי",
        "create_workspace_btn": "צור סביבת עבודה",
        "or_join_existing": "או הצטרף לקיימת",
        "join_workspace_title": "הצטרף עם קוד הזמנה",
        "join_workspace_desc": "בקש מהמנהל שלך את הקוד בן 8 התווים",
        "invite_code_label": "קוד הזמנה",
        "join_workspace_btn": "הצטרף לסביבת עבודה",
        "already_set_up": "כבר מוגדר?",
        "go_to_dashboard": "עבור ללוח הבקרה",

        # ── Workspace pending ──
        "pending_title": "הבקשה ממתינה לאישור",
        "pending_msg": "בקשתך להצטרף לסביבת העבודה נשלחה. מנהל סביבת העבודה יבדוק אותה בקרוב.",
        "pending_step1": "הבקשה נשלחה בהצלחה",
        "pending_step2": "ממתין לאישור מנהל",
        "pending_step3": "תתווסף כצופה לאחר האישור",
        "join_different_workspace": "הצטרף לסביבת עבודה אחרת",
        "sign_out_btn": "התנתק",
    },
}

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "he")


def get_translations(lang):
    return translations.get(lang, translations[DEFAULT_LANGUAGE])
