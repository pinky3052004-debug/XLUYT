import os
import io
import re
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# API Scopes Configuration
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/youtube.upload'
]

def get_gdrive_service():
    # GitHub Secrets မှ Desktop App Credentials ကို ယူခြင်း
    creds = Credentials.from_authorized_user_info(eval(os.environ['GDRIVE_CREDENTIALS']), SCOPES)
    return build('drive', 'v3', credentials=creds)

def get_youtube_service():
    # GitHub Secrets မှ Desktop App Credentials ကို ယူခြင်း
    creds = Credentials.from_authorized_user_info(eval(os.environ['YOUTUBE_CREDENTIALS']), SCOPES)
    return build('youtube', 'v3', credentials=creds)

def main():
    drive_service = get_gdrive_service()
    youtube_service = get_youtube_service()

    # ၁။ Google Drive ထဲမှ .mp4 ဖိုင်များ ရှာဖွေခြင်း
    results = drive_service.files().list(
        q="mimeType='video/mp4' and trashed=false",
        fields="files(id, name)"
    ).execute()
    items = results.get('files', [])

    # 'done_' မဟုတ်သော ဖိုင်များကို သီးသန့်ခွဲထုတ်ပြီး နံပါတ်စဉ်အလိုက် စီရန်
    pending_videos = []
    for item in items:
        name = item['name']
        if not name.startswith('done_'):
            match = re.search(r'(\d+)', name)
            file_num = int(match.group(1)) if match else float('inf')
            pending_videos.append((file_num, item))

    # ဖိုင်နံပါတ်စဉ်အလိုက် အငယ်မှ အကြီးသို့ Sort စီခြင်း (1.mp4, 2.mp4, ...)
    pending_videos.sort(key=lambda x: x[0])

    if not pending_videos:
        print("တင်ရန် ဗီဒီယိုအသစ် မတွေ့ရှိပါ။")
        return

    # တစ်ရက်စာအတွက် အများဆုံး ဗီဒီယို ၅ ဖိုင်သာ ယူမည်
    videos_to_upload = pending_videos[:5]
    
    # Schedule ပေးမည့် MMT အချိန်ဇယား (နာရီ၊ မိနစ်)
    schedule_slots = [
        (8, 30),
        (11, 30),
        (14, 30),  # 2:30 PM
        (16, 30),  # 4:30 PM
        (19, 30)   # 7:30 PM
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
                'title': f"Episode {clean_title} #Shorts",
                'description': f"Educational Video Episode {clean_title} #shorts",
                'categoryId': '27' # Education
            },
            'status': {
                'privacyStatus': 'private',  # Schedule ပေးရန် private အရင်ထားရပါမည်
                'publishAt': publish_at_iso, # သတ်မှတ်ချိန်တွင် YouTube က အလိုအလျောက် Public ပြောင်းပေးမည်
                'selfDeclaredMadeForKids': False
            }
        }

        media = MediaFileUpload(local_filename, chunksize=-1, resumable=True, mimeType='video/mp4')
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
