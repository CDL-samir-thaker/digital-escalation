import time
import certifi
import ssl
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime

# Slack configuration
SLACK_BOT_TOKEN = ""  # Replace with your bot token
ESCALATION_CHANNEL_ID = "C05BCN82N5A"  # Replace with your channel ID
MANAGER_USER_IDS = [
    "U804HBG48","UABTCMQ7N","UHWNCJW00",  # Replace with actual manager IDs
]
EYE_EMOJIS = ["eyes", "eyes-looking"]

# Initialize Slack client
client = WebClient(
    token=SLACK_BOT_TOKEN,
    ssl=ssl.create_default_context(cafile=certifi.where())
)

def log_message(message):
    """Log messages with timestamp for debugging and monitoring."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] {message}")

def check_emoji_reaction(message_ts, channel_id):
    """
    Check if an eye emoji has been added to a message.
    Returns True if the message has been acknowledged with an eye emoji.
    """
    try:
        response = client.reactions_get(channel=channel_id, timestamp=message_ts)
        has_emoji = any(reaction["name"] in EYE_EMOJIS 
                       for reaction in response["message"].get("reactions", []))
        return has_emoji
    except SlackApiError as e:
        log_message(f"Error checking reactions: {e.response['error']}")
        return False

def notify_manager(manager_id, message_text, channel_id, message_ts):
    """
    Send a formatted message to a manager with context and the message link.
    Returns True if notification was successful.
    """
    try:
        # Get message permalink
        permalink_response = client.chat_getPermalink(
            channel=channel_id,
            message_ts=message_ts
        )
        
        # Create a formatted message without exposing IDs
        notification_message = (
            ":warning: *Unacknowledged Escalation Alert* :warning:\n"
            "A business escalation has not yet been acknowledged by Tier 3 or the relevant leads. Please review this ticket and assign an appropriate Tier 3 or lead to address it. Additionally, kindly ask the individual to acknowledge this Slack message by reacting with the :eyes: icon to confirm their action\n\n"
        
            # f"{message_text}\n\n"
            "*View full escalation:*\n"
            f"{permalink_response['permalink']}"
        )
        
        result = client.chat_postMessage(
            channel=manager_id,
            text=notification_message,
            parse='full'
        )
        
        if result["ok"]:
            log_message("Successfully sent manager notification")
        return True
        
    except SlackApiError as e:
        log_message(f"Error sending manager notification: {e.response['error']}")

    """
    Send notification with user information
    """
    try:
        permalink_response = client.chat_getPermalink(
            channel=channel_id,
            message_ts=message_ts
        )
        
        # Get user who sent the message
        user_id = message.get("user", "Unknown")
        
        # Create header message
        header_message = (
            ":warning: *Unacknowledged Escalation Alert* :warning:\n"
            "A business escalation has not yet been acknowledged by Tier 3 or the relevant leads. Please review this ticket and assign an appropriate Tier 3 or lead to address it. Additionally, kindly ask the individual to acknowledge this Slack message by reacting with the :eyes: icon to confirm their action\n"
        )

        # Send header message
        client.chat_postMessage(
            channel=manager_id,
            text=header_message,
            parse='full'
        )

        # Send message content as a snippet
        client.files_upload(
            channels=manager_id,
            content=f"From: <@{user_id}>\n\n{message['text']}",
            filetype="text",
            title="Escalation Details"
        )

        # Send permalink
        footer_message = (
            "*View full escalation:*\n"
            f"{permalink_response['permalink']}"
        )
        
        result = client.chat_postMessage(
            channel=manager_id,
            text=footer_message,
            parse='full'
        )
        
        if result["ok"]:
            log_message("Successfully sent manager notification")
        return True
        
    except SlackApiError as e:
        log_message(f"Error sending manager notification: {e.response['error']}")
        return False

# def monitor_escalations():
    """
    Monitor Slack channel for escalations and notify managers periodically.
    Checks messages every 10 seconds but only notifies managers every 60 minutes.
    """
    log_message("Starting escalation monitoring...")
    checked_messages = {}  # Dictionary to store processed messages
    last_manager_notification = 0  # Timestamp of the last notification sent to managers
    
    while True:
        try:
            current_time = time.time()
            
            # Fetch the 10 most recent messages from the escalation channel
            response = client.conversations_history(
                channel=ESCALATION_CHANNEL_ID,
                limit=10
            )
            
            # List to store messages that haven't been acknowledged
            unacknowledged_messages = []
            
            for msg in response["messages"]:
                message_ts = msg["ts"]
                message_text = msg.get("text", "")
                
                # Only process messages that are escalation requests
                if "Digital Support Escalation Request" in message_text:
                    # If this is a new message we haven't seen before
                    if message_ts not in checked_messages:
                        log_message(f"New escalation found: {message_text[:100]}...")
                        checked_messages[message_ts] = {
                            "timestamp": current_time,
                            "notified": False,  # Track if managers have been notified
                            "text": message_text
                        }
                    
                    # Only check messages that are at least 1 minute old
                    if (not checked_messages[message_ts]["notified"] and 
                        current_time - checked_messages[message_ts]["timestamp"] >= 60):
                        
                        # Check if message has an eyes emoji reaction
                        if not check_emoji_reaction(message_ts, ESCALATION_CHANNEL_ID):
                            log_message(f"No acknowledgment found for message {message_ts}")
                            # Add to list of messages needing attention
                            unacknowledged_messages.append({
                                "text": checked_messages[message_ts]["text"],
                                "ts": message_ts
                            })
                        else:
                            # Message was acknowledged, remove from tracking
                            log_message(f"Message {message_ts} has been acknowledged")
                            checked_messages.pop(message_ts, None)
            
            # Only send notifications if conditions are met
            if unacknowledged_messages and (current_time - last_manager_notification >= 3600):
                for manager_id in MANAGER_USER_IDS:
                    # Notify each manager about each unacknowledged message
                    for msg in unacknowledged_messages:
                        notify_manager(
                            manager_id,
                            msg,
                            ESCALATION_CHANNEL_ID,
                            msg["ts"]
                        )
                # Update the last notification timestamp
                last_manager_notification = current_time
                
                # Mark all notified messages as processed
                for msg in unacknowledged_messages:
                    if msg["ts"] in checked_messages:
                        checked_messages[msg["ts"]]["notified"] = True
            
            # Clean up: remove messages that are no longer in the channel
            current_messages = {msg["ts"] for msg in response["messages"]}
            checked_messages = {
                ts: data for ts, data in checked_messages.items() 
                if ts in current_messages
            }
            
            # Wait 10 seconds before next check
            time.sleep(10)
            
        except SlackApiError as e:
            log_message(f"Slack API Error: {e.response['error']}")
            time.sleep(60)
        except Exception as e:
            log_message(f"Unexpected error: {str(e)}")
            time.sleep(60)

def monitor_escalations():
    """
    Monitor Slack channel for escalations and notify managers periodically.
    Checks messages every 10 seconds but only notifies managers every 60 minutes.
    """
    log_message("Starting escalation monitoring...")
    checked_messages = {}  # Dictionary to store processed messages
    last_manager_notification = 0  # Timestamp of the last notification sent to managers
    
    while True:
        try:
            current_time = time.time()
            
            # Fetch the 10 most recent messages from the escalation channel
            response = client.conversations_history(
                channel=ESCALATION_CHANNEL_ID,
                limit=10
            )
            
            # List to store messages that haven't been acknowledged
            unacknowledged_messages = []
            
            for msg in response["messages"]:
                message_ts = msg["ts"]
                
                # Only process messages that are escalation requests
                if "Digital Support Escalation Request" in msg.get("text", ""):
                    # If this is a new message we haven't seen before
                    if message_ts not in checked_messages:
                        log_message(f"New escalation found: {msg.get('text', '')[:100]}...")
                        checked_messages[message_ts] = {
                            "timestamp": current_time,
                            "notified": False,  # Track if managers have been notified
                        }
                    
                    # Only check messages that are at least 60 minutes old
                    if (not checked_messages[message_ts]["notified"] and 
                        current_time - checked_messages[message_ts]["timestamp"] >= 3600):  # Changed to 3600 seconds (60 minutes)
                        
                        # Check if message has an eyes emoji reaction
                        if not check_emoji_reaction(message_ts, ESCALATION_CHANNEL_ID):
                            log_message(f"No acknowledgment found for message {message_ts}")
                            # Add to list of messages needing attention
                            unacknowledged_messages.append(msg)
                        else:
                            # Message was acknowledged, remove from tracking
                            log_message(f"Message {message_ts} has been acknowledged")
                            checked_messages.pop(message_ts, None)
            
            # Only send notifications if conditions are met
            if unacknowledged_messages and (current_time - last_manager_notification >= 3600):  # 60 minutes between notifications
                for manager_id in MANAGER_USER_IDS:
                    # Notify each manager about each unacknowledged message
                    for msg in unacknowledged_messages:
                        notify_manager(
                            manager_id,
                            msg,
                            ESCALATION_CHANNEL_ID,
                            msg["ts"]
                        )
                # Update the last notification timestamp
                last_manager_notification = current_time
                
                # Mark all notified messages as processed
                for msg in unacknowledged_messages:
                    if msg["ts"] in checked_messages:
                        checked_messages[msg["ts"]]["notified"] = True
            
            # Clean up: remove messages that are no longer in the channel
            current_messages = {msg["ts"] for msg in response["messages"]}
            checked_messages = {
                ts: data for ts, data in checked_messages.items() 
                if ts in current_messages
            }
            
            # Wait 10 seconds before next check
            time.sleep(10)
            
        except SlackApiError as e:
            log_message(f"Slack API Error: {e.response['error']}")
            time.sleep(60)
        except Exception as e:
            log_message(f"Unexpected error: {str(e)}")
            time.sleep(60)


if __name__ == "__main__":
    try:
        monitor_escalations()
    except KeyboardInterrupt:
        log_message("Monitoring stopped by user")
    except Exception as e:
        log_message(f"Fatal error: {str(e)}")
    finally:
        log_message("Exiting...")
