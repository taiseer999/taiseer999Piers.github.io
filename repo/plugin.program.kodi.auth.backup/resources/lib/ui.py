import xbmcgui
from .utils import detect_addons, get_addon_name
from .backup import run_backup
from .restore import list_backup_addons, run_restore
from .config import BACKUP_ROOT

D = xbmcgui.Dialog()
TITLE = "Kodi Auth Backup"
ABOUT_TEXT = """Kodi Auth Backup

Developed by: i-Meshal

Telegram:
@i_meshal

GitHub:
https://github.com/i-Meshal/Kodi-Auth-Backup
"""

def run():
    while True:
        c = D.select(TITLE, [
            " نسخ احتياطي سريع (الكل)",
            " نسخ احتياطي مخصص",
            " استعادة (Restore)",
            " عن المطور",
            " خروج"
        ])

        if c == 0:
            addons = detect_addons()
            path = D.browse(3, "اختر مسار حفظ النسخة", "files") or str(BACKUP_ROOT)
            zip_path = run_backup(path, addons)
            if zip_path and zip_path.exists():
                D.ok("تم بنجاح", f"تم إنشاء النسخة الاحتياطية بنجاح في:\n{zip_path}")

        elif c == 1:
            addons = detect_addons()
            names = [get_addon_name(a) for a in addons]
            idx = D.multiselect("حدد الإضافات للنسخ الاحتياطي", names)
            
            if not idx: # إذا ضغط المستخدم إلغاء
                continue

            selected = [addons[i] for i in idx]
            path = D.browse(3, "اختر مسار حفظ النسخة", "files") or str(BACKUP_ROOT)
            zip_path = run_backup(path, selected)
            if zip_path and zip_path.exists():
                D.ok("تم بنجاح", f"تم النسخ المخصص بنجاح:\n{zip_path}")

        elif c == 2:
            file = D.browse(1, "اختر ملف النسخة الاحتياطية (Zip)", "files", ".zip")
            if not file:
                continue

            mode = D.select("نوع الاستعادة", [
                "استعادة شاملة (Full)",
                "استعادة مخصصة (Partial)"
            ])
            if mode < 0:
                continue

            restore_method = D.select("طريقة استعادة settings.xml", [
                "دمج مفاتيح التوثيق فقط",
                "استبدال ملف settings.xml كامل"
            ])
            if restore_method < 0:
                continue

            auth_only = restore_method == 0

            if mode == 0:
                run_restore(file, auth_only=auth_only, settings_only=not auth_only)
                if auth_only:
                    D.ok("تم بنجاح", "تم دمج مفاتيح التوثيق فقط. قد تحتاج لإعادة تشغيل كودي.")
                else:
                    D.ok("تم بنجاح", "تم استبدال ملفات settings.xml. قد تحتاج لإعادة تشغيل كودي.")
            elif mode == 1:
                addons = list_backup_addons(file)
                if not addons:
                    D.ok("تنبيه", "لم يتم العثور على إضافات قابلة للاستعادة داخل ملف النسخة.")
                    continue

                names = [get_addon_name(a) for a in addons]
                idx = D.multiselect("حدد الإضافات لاستعادتها", names)
                
                if not idx:
                    continue

                selected = [addons[i] for i in idx]
                run_restore(file, "partial", selected, auth_only=auth_only, settings_only=not auth_only)
                if auth_only:
                    D.ok("تم بنجاح", "تم دمج مفاتيح التوثيق المحددة فقط.")
                else:
                    D.ok("تم بنجاح", "تم استبدال ملفات settings.xml المحددة.")

        elif c == 3:
            D.textviewer("عن المطور", ABOUT_TEXT)

        else:
            break
