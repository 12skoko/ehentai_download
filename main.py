from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
import subprocess
import smtplib
from email.mime.text import MIMEText
import re
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


def run_py(py_cmd, mark_name):
    time = datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
    print(mark_name + ':' + time)
    output_file = f"./log/{mark_name}_{time}.txt"
    with open(output_file, "a", encoding='utf-8') as f:
        try:
            run_cmd = [config.python_path] + py_cmd.split(' ')
            result = subprocess.run(run_cmd, check=True, stdout=f,
                                    stderr=subprocess.PIPE, universal_newlines=True)
            # print(result.stdout)
        except subprocess.CalledProcessError as e:
            tqdm_pattern = re.compile(r'\s*\d+%\|.*?\| \d+.?\d+[kMG]/\d+.?\d+[kMG] \[\d+:\d+:?\d+?<\d+:\d+:?\d+?, \d+.\d+?[kM]?iB/s]\s*')
            tqdm_pattern2 = re.compile(r'\s*0%\|\s*\| 0.00/\d+.?\d+[kMG] \[00:00<\?, \?iB/s]')
            error_content = e.stderr
            error_content = re.sub(tqdm_pattern, "", error_content)
            error_content = re.sub(tqdm_pattern2, "", error_content)
            print(str(run_cmd))
            f.write('\n\n\n' + str(run_cmd) + '\n\n\n' + error_content)
            f.close()
            py_name = py_cmd.split(' ')[0]
            subject = "EH download error"
            with open(output_file, "r", encoding='utf-8') as ft:
                context = ft.read()
            message = time + '---' + py_name + " error" + '\n\n' + str(run_cmd) + '\n\n' + context
            sendEmail(config.sender_email, config.email_auth, config.rec_email, subject, message)
            scheduler.shutdown()
            raise 'run_py error'


start_date = datetime.now() + timedelta(seconds=1)
scheduler = BlockingScheduler()

scheduler.add_job(run_py, args=("collect.py", "collect"), trigger='interval', hours=6, seconds=7, start_date=start_date)
scheduler.add_job(run_py, args=("download_torrent.py --main", "downloadTorrent"), trigger='interval', hours=2,
                  seconds=3, start_date=start_date)
scheduler.add_job(run_py, args=("download_hah.py --main --direct", "downloadHah"), trigger='interval', hours=2, seconds=2,
                  start_date=start_date)
scheduler.add_job(run_py, args=("complete_download.py --main", "completeDownload"), trigger='interval', hours=1,
                  seconds=1, start_date=start_date)

scheduler.start()
