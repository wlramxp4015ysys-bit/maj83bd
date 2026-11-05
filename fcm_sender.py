"""
Firebase Cloud Messaging (FCM) Push Notification Sender for AHMAD TV.
Sends high-priority push notifications to registered devices, supporting background delivery,
app icon, custom sound, and invalid token cleanup.
"""

import json
import time
import urllib.request
import urllib.error
from config import FIREBASE_SERVER_KEY, FIREBASE_PROJECT_ID, logger
from database import db

FCM_LEGACY_URL = "https://fcm.googleapis.com/fcm/send"

def is_firebase_configured():
    return bool(FIREBASE_SERVER_KEY and len(FIREBASE_SERVER_KEY.strip()) > 10)

def send_fcm_notification(title, message, image_url=None, sound_url=None, target_tokens=None, extra_data=None):
    """
    Sends a push notification via Firebase Cloud Messaging (FCM).
    If target_tokens is None, retrieves all active tokens from database.
    Chunks into batches of 1,000 devices per request.
    """
    title = str(title).strip() if title else "AHMAD TV"
    message = str(message).strip() if message else ""

    if target_tokens is None:
        target_tokens = db.get_all_fcm_tokens()

    result = {
        "configured": is_firebase_configured(),
        "total_targets": len(target_tokens),
        "success": 0,
        "failed": 0,
        "cleaned_invalid_tokens": 0,
        "mode": "fcm" if is_firebase_configured() else "local_queue"
    }

    if not is_firebase_configured():
        logger.warning("FCM: FIREBASE_SERVER_KEY is not set in .env. Notification queued for active app clients.")
        return result

    if not target_tokens:
        # Also attempt sending to general topic if no direct tokens
        send_to_topic("all_users", title, message, image_url, sound_url, extra_data)
        logger.info("FCM: No individual device tokens registered. Broadcast sent to topic 'all_users'.")
        return result

    # Batch tokens up to 1000 per request (FCM limit)
    BATCH_SIZE = 1000
    invalid_tokens = []

    for i in range(0, len(target_tokens), BATCH_SIZE):
        batch = target_tokens[i:i + BATCH_SIZE]

        notification_payload = {
            "title": title,
            "body": message,
            "sound": "default",
            "android_channel_id": "a2_tv_push_channel_v2",
            "icon": "ic_launcher"
        }
        if image_url:
            notification_payload["image"] = image_url

        data_payload = {
            "title": title,
            "message": message,
            "image": image_url or "",
            "sound": sound_url or "",
            "timestamp": str(int(time.time())),
            "click_action": "OPEN_MAIN_ACTIVITY"
        }
        if extra_data and isinstance(extra_data, dict):
            data_payload.update(extra_data)

        payload = {
            "registration_ids": batch,
            "priority": "high",
            "notification": notification_payload,
            "data": data_payload
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                FCM_LEGACY_URL,
                data=req_data,
                headers={
                    "Authorization": f"key={FIREBASE_SERVER_KEY}",
                    "Content-Type": "application/json"
                }
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                success = resp_json.get("success", 0)
                failure = resp_json.get("failure", 0)
                result["success"] += success
                result["failed"] += failure

                results = resp_json.get("results", [])
                for idx, item in enumerate(results):
                    err = item.get("error")
                    if err in ("NotRegistered", "InvalidRegistration", "MismatchSenderId"):
                        if idx < len(batch):
                            invalid_tokens.append(batch[idx])

                logger.info("FCM batch dispatched: %d succeeded, %d failed", success, failure)

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            logger.error("FCM HTTPError %d: %s", e.code, err_body)
            result["failed"] += len(batch)
        except Exception as e:
            logger.error("FCM dispatch error: %s", str(e))
            result["failed"] += len(batch)

    if invalid_tokens:
        removed = db.remove_invalid_tokens(invalid_tokens)
        result["cleaned_invalid_tokens"] = removed

    # Also broadcast to topic 'all_users'
    send_to_topic("all_users", title, message, image_url, sound_url, extra_data)

    return result

def send_to_topic(topic, title, message, image_url=None, sound_url=None, extra_data=None):
    if not is_firebase_configured():
        return False
    try:
        notification_payload = {
            "title": title,
            "body": message,
            "sound": "default",
            "android_channel_id": "a2_tv_push_channel_v2",
            "icon": "ic_launcher"
        }
        if image_url:
            notification_payload["image"] = image_url

        data_payload = {
            "title": title,
            "message": message,
            "image": image_url or "",
            "sound": sound_url or "",
            "timestamp": str(int(time.time())),
            "click_action": "OPEN_MAIN_ACTIVITY"
        }
        if extra_data and isinstance(extra_data, dict):
            data_payload.update(extra_data)

        payload = {
            "to": f"/topics/{topic}",
            "priority": "high",
            "notification": notification_payload,
            "data": data_payload
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            FCM_LEGACY_URL,
            data=req_data,
            headers={
                "Authorization": f"key={FIREBASE_SERVER_KEY}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            logger.info("FCM topic message sent to /topics/%s", topic)
            return True
    except Exception as e:
        logger.warning("FCM topic dispatch error: %s", str(e))
        return False
