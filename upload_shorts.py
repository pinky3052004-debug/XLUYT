import os
import io
import re
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/youtube.force-ssl'
]

FOLDER_NAME = "XsuuLin" # သင်သတ်မှတ်ထားသော ဖိုဒါအမည်

def get_gdrive_service():
    creds = Credentials.from_authorized_user_info(eval(os.environ['GDRIVE_CREDENTIALS']), SCOPES)
    return build('drive', 'v3', credentials=creds)

def get_youtube_service():
    creds = Credentials.from_authorized_user_info(eval(os.environ['YOUTUBE_CREDENTIALS']), SCOPES)
    return build('youtube', 'v3', credentials=creds)

def get_folder_id(drive_service, folder_name):
    """ဖိုဒါအမည်ဖြင့် ၎င်း၏ Drive Folder ID ကို ရှာဖွေခြင်း"""
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    results = drive_service.files().list(q=query, fields="files(id)").execute()
    items = results.get('files', [])
    if not items:
        raise Exception(f"Google Drive တွင် '{folder_name}' ဆိုသည့် ဖိုဒါ မတွေ့ရှိပါ။")
    return items[0]['id']

def main():
    drive_service = get_gdrive_service()
    youtube_service = get_youtube_service()

    # ၁။ XsuuLin ဖိုဒါ၏ ID ကို ယူခြင်း
    try:
        folder_id = get_folder_id(drive_service, FOLDER_NAME)
        print(f"ဖိုဒါ တွေ့ရှိပါပြီ - {FOLDER_NAME} (ID: {folder_id})")
    except Exception as e:
        print(e)
        return

    # ၂။ သတ်မှတ်ထားသော ဖိုဒါအတွင်းမှသာ .mp4 ဖိုင်များ ရှာဖွေခြင်း
    query = f"'{folder_id}' in parents and mimeType='video/mp4' and trashed=false"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    pending_videos = []
    for item in items:
        name = item['name']
        if not name.startswith('done_'):
            match = re.search(r'(\d+)', name)
            file_num = int(match.group(1)) if match else float('inf')
            pending_videos.append((file_num, item))

    pending_videos.sort(key=lambda x: x[0])

    if not pending_videos:
        print(f"'{FOLDER_NAME}' ဖိုဒါထဲတွင် တင်ရန် ဗီဒီယိုအသစ် မတွေ့ရှိပါ။")
        return

    videos_to_upload = pending_videos[:5]
    
    schedule_slots = [(8, 30), (11, 30), (14, 30), (16, 30), (19, 30)]
    mmt_tz = timezone(timedelta(hours=6, minutes=30))
    today = datetime.now(mmt_tz)

    for index, (file_num, item) in enumerate(videos_to_upload):
        video_id = item['id']
        video_name = item['name']
        clean_title = os.path.splitext(video_name)[0]
        local_filename = f"temp_{video_name}"

        hour, minute = schedule_slots[index]
        slot_time = today.replace(hour=hour, minute=minute, second=0, microsecond=0)
        utc_slot_time = slot_time.astimezone(timezone.utc)
        publish_at_iso = utc_slot_time.strftime('%Y-%m-%dT%H:%M:%SZ')

        print(f"\n[{index+1}/{len(videos_to_upload)}] ဒေါင်းလုဒ်ဆွဲနေသည်: {video_name}")

        # ဗီဒီယို ဒေါင်းလုဒ်ချခြင်း
        request = drive_service.files().get_media(fileId=video_id)
        fh = io.FileIO(local_filename, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        # YouTube သို့ Schedule ဖြင့် တင်ခြင်း
        print(f"YouTube တွင် Schedule သတ်မှတ်နေသည် - အချိန်: MMT {hour}:{minute}")
        body = {
            'snippet': {
                'title': f"Episode {clean_title} #Shorts",
                'description': f"Educational Video Episode {clean_title} #shorts",
                'categoryId': '27'
            },
            'status': {
                'privacyStatus': 'private',
                'publishAt': publish_at_iso,
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

        print(f"Schedule အောင်မြင်သည်။ Video ID: {response['id']}")

        # Drive ပေါ်တွင် နာမည်ပြောင်းလဲခြင်း
        new_name = f"done_{video_name}"
        drive_service.files().update(fileId=video_id, body={'name': new_name}).execute()
        print(f"Drive တွင် နာမည်ပြောင်းလဲပြီးပါပြီ: {new_name}")

        if os.path.exists(local_filename):
            os.remove(local_filename)

if __name__ == '__main__':
    main()
