import xbmcvfs
from pathlib import Path

# استخدام xbmcvfs لجعل الإضافة متوافقة مع كل الأنظمة (Android, Windows, CoreELEC)
userdata_path = xbmcvfs.translatePath("special://userdata/")
KODI = Path(userdata_path)

# مسار الحفظ الافتراضي (يمكن تركه لـ CoreELEC ولكن يفضل تغييره من قبل المستخدم)
BACKUP_ROOT = Path("/storage/backups")