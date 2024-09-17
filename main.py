from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
import subprocess
import smtplib
from email.mime.text import MIMEText
import config


def sendEmail(sender_email, email_auth, rec_email, subject, message):
    msg = MIMEText(message)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['to'] = rec_email
    with smtplib.SMTP_SSL(config.smtp_url, config.smtp_port) as smtp:
        smtp.login(sender_email, email_auth)
        smtp.send_message(msg)
        print('sendEmail Success')


def run_py(py_name, mark_name):
    time = datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
    print(mark_name + ':' + time)
    output_file = f"./log/{mark_name}_{time}.txt"
    with open(output_file, "a", encoding='utf-8') as f:
        try:
            result = subprocess.run([config.python_path, py_name], check=True, stdout=f,
                                    stderr=subprocess.PIPE, universal_newlines=True)
            # print(result.stdout)
        except subprocess.CalledProcessError as e:
            f.write('\n\n\n' + e.stderr)
            f.close()
            subject = time + '---' + py_name + " error"
            with open(output_file, "r", encoding='utf-8') as ft:
                context = ft.read()
            message = context + '\n\n\n' + e.stderr
            sendEmail(config.sender_email, config.email_auth, config.rec_email, subject, message)
            scheduler.shutdown()
            exit(666)


start_date = datetime.now() + timedelta(seconds=1)
scheduler = BlockingScheduler()

scheduler.add_job(run_py, args=("collect.py", "collect"), trigger='interval', hours=6, seconds=7, start_date=start_date)
scheduler.add_job(run_py, args=("downloadTorrent.py", "downloadTorrent"), trigger='interval', hours=2, seconds=3, start_date=start_date)
scheduler.add_job(run_py, args=("downloadHah.py", "downloadHah"), trigger='interval', hours=2, seconds=2, start_date=start_date)
scheduler.add_job(run_py, args=("completeDownload.py", "completeDownload"), trigger='interval', hours=1, seconds=1, start_date=start_date)

scheduler.start()
