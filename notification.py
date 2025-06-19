import smtplib
import datetime
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_email_notification(recipients, subject, body):
    if not recipients:
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = "eplumber@localhost"
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP("localhost", 25)
        server.sendmail("eplumber@localhost", recipients, msg.as_string())
        server.quit()

        logger.info(f"Email notification sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email notification '{subject}': {e}")


def send_action_notification(recipients, action_name, rule_context=None):
    subject = f"Eplumber Action: {action_name}"

    body = f"Action '{action_name}' has been executed.\nTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    if rule_context:
        body += f"Rule: {rule_context.name}\n\nTest Results:\n"
        for test in rule_context.tests:
            current_value = test.sensor.mean
            if isinstance(current_value, float):
                current_value = round(current_value, 2)
            passes = (
                test.operator(current_value, test.value)
                if current_value is not None
                else False
            )
            status = "✅ PASS" if passes else "❌ FAIL"
            body += (
                f"  {status} {test.sensor.name}: {current_value} {test.op} {test.value}\n"
            )

    send_email_notification(recipients, subject, body)


def send_startup_notification(recipients):
    subject = "Eplumber Started"
    body = f"Eplumber IoT automation system has started successfully.\nTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    send_email_notification(recipients, subject, body)
