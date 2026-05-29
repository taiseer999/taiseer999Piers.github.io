import zipfile, json
import xbmcgui
from datetime import datetime
from pathlib import Path
from .config import KODI
from .logger import logger
from .accounts import export_accounts

# تمت إضافة أهم ملفات كودي للحفظ
IMPORTANT_FILES = ["settings.xml", "sources.xml", "advancedsettings.xml", "passwords.xml", "favourites.xml"]
TITLE = "Kodi Auth Backup"

def run_backup(dest_path, selected_addons):
    backup_name = datetime.now().strftime("backup_%Y-%m-%d_%H-%M.zip")
    zip_path = Path(dest_path) / backup_name

    logger.info("Backup started")
    
    # واجهة شريط التقدم الشكلية
    dp = xbmcgui.DialogProgress()
    dp.create(TITLE, "جاري تجهيز النسخ الاحتياطي...")

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
            total_items = len(selected_addons) + 2 # Addons + guisettings + accounts
            current_item = 0

            for addon in selected_addons:
                if dp.iscanceled():
                    break
                
                percent = int((current_item / total_items) * 100)
                dp.update(percent, f"جاري نسخ: {addon}")
                
                src = KODI / "addon_data" / addon
                for f in IMPORTANT_FILES:
                    full = src / f
                    if full.exists():
                        z.write(full, full.relative_to(KODI))
                current_item += 1

            # نسخ الإعدادات العامة
            dp.update(int((current_item / total_items) * 100), "نسخ الإعدادات العامة (guisettings)...")
            gs = KODI / "guisettings.xml"
            if gs.exists():
                z.write(gs, gs.relative_to(KODI))
            current_item += 1

            # نسخ الحسابات
            dp.update(int((current_item / total_items) * 100), "استخراج الحسابات والمفاتيح...")
            acc_data = export_accounts(selected_addons)
            z.writestr("accounts.json", json.dumps(acc_data, ensure_ascii=False, indent=2))
            
    except Exception as e:
        logger.error(f"Backup failed: {str(e)}")
        xbmcgui.Dialog().ok("خطأ", f"حدث خطأ أثناء النسخ:\n{str(e)}")
    finally:
        dp.close()

    logger.info(f"Backup done: {zip_path}")
    return zip_path
