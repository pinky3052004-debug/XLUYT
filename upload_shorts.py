import os
import io
import re
import json  # JSON string များကို စိတ်ချရစွာ parse လုပ်ရန်
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# --- Google Drive Service (သီးသန့် Scope ဖြင့် ခွဲထုတ်ထားပါသည်) ---
def get_gdrive_service():
    DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']
    creds_data = json.loads(os.environ['GDRIVE_CREDENTIALS'])
    creds = Credentials.from_authorized_user_info(creds_data, DRIVE_SCOPES)
    return build('drive', 'v3', credentials=creds)

# --- YouTube Service (သီးသန့် Scope ဖြင့် ခွဲထုတ်ထားပါသည်) ---
def get_youtube_service():
    YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
    creds_data = json.loads(os.environ['YOUTUBE_CREDENTIALS'])
    creds = Credentials.from_authorized_user_info(creds_data, YOUTUBE_SCOPES)
    return build('youtube', 'v3', credentials=creds)

def main():
    # GitHub Secrets မှ Folder ID ကို လှမ်းယူခြင်း
    folder_id = os.environ.get('GDRIVE_FOLDER_ID')
    
    if not folder_id:
        print("Error: GDRIVE_FOLDER_ID ကို GitHub Secrets တွင် မသတ်မှတ်ရသေးပါ။")
        return

    drive_service = get_gdrive_service()
    youtube_service = get_youtube_service()

    print(f"သတ်မှတ်ထားသော Folder ID အတွင်းမှ ဖိုင်များကို စစ်ဆေးနေသည်...")

    # ၁။ GitHub Secrets မှရလာသော Folder ID အတွင်းမှ .mp4 ဖိုင်များ ရှာဖွေခြင်း
    query = f"'{folder_id}' in parents and mimeType='video/mp4' and trashed=false"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    # 'done_' မဟုတ်သော ဖိုင်များကို သီးသန့်ခွဲထုတ်ပြီး နံပါတ်ကို ရှာဖွေခြင်း
    pending_videos = []
    for item in items:
        name = item['name']
        # 💡 တင်ပြီးသားဖိုင်များကို ကျော်ရန် 'done_' ကို စစ်ဆေးပါသည်
        if not name.startswith('done_'):
            match = re.search(r'(\d+)', name)
            file_num = int(match.group(1)) if match else float('inf')
            pending_videos.append((file_num, item))

    # 💡 ဤနေရာတွင် ဖိုင်နံပါတ်စဉ်အလိုက် အငယ်မှ အကြီးသို့ (1, 2, 3...) တိတိကျကျ စီပေးပါသည်
    pending_videos.sort(key=lambda x: x[0])

    if not pending_videos:
        print("တင်ရန် ဗီဒီယိုအသစ် မတွေ့ရှိပါ။")
        return

    # တစ်ရက်စာအတွက် အများဆုံး ဗီဒီယို ၅ ဖိုင်သာ ယူမည်
    videos_to_upload = pending_videos[:5]
    
    # Schedule ပေးမည့် MMT အချိန်ဇယား (နာရီ၊ မိနစ်)
    schedule_slots = [
        (20, 30),
        (21, 30),
        (22, 30),  
        (23, 30),  
        (0, 30)    # 💡 ညသန်းခေါင်ကျော်အတွက် 24 အစား 0 သို့ ပြောင်းလဲထားပါသည်
    ]

    # ယနေ့ ရက်စွဲအား MMT Timezone (UTC+6:30) ဖြင့် ရယူခြင်း
    mmt_tz = timezone(timedelta(hours=6, minutes=30))
    today = datetime.now(mmt_tz)

    for index, (file_num, item) in enumerate(videos_to_upload):
        video_id = item['id']
        video_name = item['name']
        clean_title = os.path.splitext(video_name)[0]
        local_filename = f"temp_{video_name}"

        # သက်ဆိုင်ရာ Slot အလိုက် Schedule အချိန် သတ်မှတ်ခြင်း
        hour, minute = schedule_slots[index]
        slot_time = today.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # 💡 နာရီက 0 နာရီ (ညသန်းခေါင်ကျော်) ဖြစ်ပါက ရက်စွဲအား နောက်တစ်နေ့သို့ ၁ ရက် တိုးပေးပါသည်
        if hour == 0:
            slot_time = slot_time + timedelta(days=1)
        
        # YouTube API အတွက် MMT မှ UTC သို့ ပြောင်းလဲပြီး ISO Format String ပြုလုပ်ခြင်း
        utc_slot_time = slot_time.astimezone(timezone.utc)
        publish_at_iso = utc_slot_time.strftime('%Y-%m-%dT%H:%M:%SZ')

        print(f"\n[{index+1}/{len(videos_to_upload)}] ဒေါင်းလုဒ်ဆွဲနေသည်: {video_name}")

        # ၂။ Google Drive မှ Local သို့ ဗီဒီယို ဒေါင်းလုဒ်ချခြင်း
        request = drive_service.files().get_media(fileId=video_id)
        fh = io.FileIO(local_filename, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        # ၃။ YouTube သို့ Schedule ဖြင့် Upload တင်ခြင်း
        print(f"YouTube တွင် Schedule သတ်မှတ်နေသည် - အချိန်: MMT {hour}:{minute} (UTC {publish_at_iso})")
        body = {
            'snippet': {
                'title': f"#XsuuLin #Shorts #DanceShorts #ViralDance #TrendingDance #DanceChallenge #DanceTrends #TikTokDance",
                'description': f"#XsuuLin #Shorts #DanceShorts #ViralDance #TrendingDance #DanceChallenge #DanceTrends #TikTokDance #DanceCompilation #FYP #ForYou #TrendingNow #NewDanceTrend",
                'categoryId': '24' # Entertainment
            },
            'status': {
                'privacyStatus': 'private',  # Schedule ပေးရန် private အရင်ထားရပါမည်
                'publishAt': publish_at_iso, # သတ်မှတ်ချိန်တွင် YouTube က အလိုအလျောက် Public ပြောင်းပေးမည်
                'selfDeclaredMadeForKids': False
            }
        }

        # 💡 mimeType အစား မှန်ကန်သော စာလုံးပေါင်း mimetype သို့ ပြောင်းလဲထားပါသည်
        media = MediaFileUpload(local_filename, chunksize=-1, resumable=True, mimetype='video/mp4')
        upload_request = youtube_service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = upload_request.next_chunk()

        print(f"Schedule လုပ်ဆောင်ချက် အောင်မြင်သည်။ Video ID: {response['id']}")

        # ၄။ Google Drive ပေါ်တွင် 'done_' prefix ဖြင့် နာမည်ပြောင်းလဲ၍ သိမ်းဆည်းခြင်း
        new_name = f"done_{video_name}"
        drive_service.files().update(fileId=video_id, body={'name': new_name}).execute()
        print(f"Drive တွင် နာမည်ပြောင်းလဲပြီးပါပြီ: {new_name}")

        # Local ဒေါင်းလုဒ်ဖိုင်အား ရှင်းလင်းခြင်း
        if os.path.exists(local_filename):
            os.remove(local_filename)

if __name__ == '__main__':
    main()
