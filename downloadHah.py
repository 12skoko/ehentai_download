import time
import requests
import re
import random
import config
import datetime
from bs4 import BeautifulSoup
from TagTranslation import EhTagTranslation
import html
import os
from tqdm import tqdm


def check_complete(base_directory, partial_directory_name, file_name="galleryinfo.txt"):
    for item in os.listdir(base_directory):
        item_path = os.path.join(base_directory, item)
        if os.path.isdir(item_path) and partial_directory_name in item:
            # 检查目录中是否存在指定的文件
            for file_item in os.listdir(item_path):
                if os.path.isfile(os.path.join(item_path, file_item)) and file_item == file_name:
                    return True, item
    return False, ""


def getRealname(name):
    length = len(name)
    s = 0
    m = 0
    l = 0
    r = length
    for i in range(length):
        ch = name[i]
        if (s == 0 and m == 0) and (ch != '(' and ch != '[' and ch != ' '):
            l = i
            break
        elif ch == '(':
            s += 1
        elif ch == '[':
            m += 1
        elif ch == ')':
            s -= 1
        elif ch == ']':
            m -= 1
    for i in range(length - 1, -1, -1):
        ch = name[i]
        if (s == 0 and m == 0) and (ch != ')' and ch != ']' and ch != ' '):
            r = i + 1
            break
        elif ch == ')':
            s += 1
        elif ch == ']':
            m += 1
        elif ch == '(':
            s -= 1
        elif ch == '[':
            m -= 1
    realname = name[l:r]
    return realname


def parseinfo(html):
    soup = BeautifulSoup(html, 'lxml')
    name = soup.find("h1", id="gj").text.replace('"', '""')
    romaname = soup.find("h1", id="gn").text.replace('"', '""')
    if name == '':
        name = romaname
        romaname = ''
    category = soup.find("div", id="gdc").text
    uploader = soup.find("div", id="gdn").text
    bs_td = soup.find_all("td", class_="gdt2")
    postedtime = bs_td[0].text
    parent = bs_td[1].text
    language = bs_td[3].text.replace("\xa0", "")
    estimatedsize = bs_td[4].text
    pages = int(bs_td[5].text.replace(" pages", ""))
    favorited = int(bs_td[6].text.replace(" times", "").replace("Once", "1").replace("Never", "0"))
    rating_count = int(soup.find("span", id="rating_count").text)
    rating = int(float(soup.find("td", id="rating_label").text.replace("Average: ", "")) * 100)
    tagstrings = soup.find("div", id="taglist")
    taglist = []
    for text in tagstrings.strings:
        if ':' in text:
            row = text
        else:
            taglist.append(row + text)
    tag = ','.join(taglist)
    # div=soup.find('div', id='gd5')
    # p_element = soup.find('p', class_='g2 gsp')
    onclick_value = soup.find('a', href="#", string='Archive Download').get('onclick')
    # print(a_element)
    # onclick_value = a_element
    downloadlink = re.search("return popUp\('(https:\/\/exhentai\.org\/archiver\.php.*?)',480,320\)", onclick_value)[1]
    return name, romaname, category, uploader, postedtime, language, estimatedsize, pages, favorited, rating_count, rating, tag, downloadlink, parent


def parse_file_size(size_str):
    units = {"B": 1, "KiB": 1024, "MiB": 1048576, "GiB": 1073741824, "TiB": 1099511627776}
    size, unit = float(size_str[:-4]), size_str[-3:]
    return size * units[unit]


# def download_file(url, filename, retries=3, min_speed=30, check_interval=5):
#     """
#     下载文件并监控下载速度，支持错误和速度低于阈值时的重试机制。
#
#     :param url: 下载链接
#     :param filename: 文件保存路径
#     :param retries: 最大重试次数
#     :param min_speed: 速度阈值 (kB/s)
#     :param check_interval: 检查速度的间隔时间 (秒)
#     """
#     attempt = 0
#     while attempt < retries:
#         try:
#             response = requests.get(url, headers=config.header, stream=True, proxies=config.proxies1)
#             response.raise_for_status()
#             total_size = int(response.headers.get('content-length', 0))
#             block_size = 1024
#
#             progress_bar = tqdm(total=total_size, unit='iB', unit_scale=True)
#             start_time = time.time()
#             downloaded_size = 0
#
#             with open(filename, 'wb') as file:
#                 for data in response.iter_content(block_size):
#                     file.write(data)
#                     progress_bar.update(len(data))
#                     downloaded_size += len(data)
#
#                     # 检查下载速度
#                     elapsed_time = time.time() - start_time
#                     if elapsed_time >= check_interval:
#                         speed = (downloaded_size / 1024) / elapsed_time  # kB/s
#                         if speed < min_speed:
#                             raise Exception(f"Download speed too low: {speed:.2f} kB/s")
#                         start_time = time.time()  # 重置计时
#                         downloaded_size = 0
#
#             progress_bar.close()
#
#             if total_size != 0 and progress_bar.n != total_size:
#                 raise Exception("ERROR: download error - file size mismatch")
#
#             print("Download completed successfully.")
#             return  # 成功下载后退出函数
#
#         except (ConnectionError, Exception) as e:
#             attempt += 1
#             try:
#                 progress_bar.close()  # 确保进度条关闭
#             except:
#                 pass
#             print(f"Download attempt {attempt}/{retries} failed: {e}")
#             if attempt < retries:
#                 print("Retrying...")
#                 time.sleep(200)  # 等待一段时间后重试
#             else:
#                 raise "Max retries reached. Raising error to terminate program."  # 超过重试次数后抛出异常终止程序


def download_aria2(url, file_name, checkout=0):
    json_rpc_data = {
        'jsonrpc': '2.0',
        'method': 'aria2.addUri',
        'id': 'qwer',
        'params': [
            f'token:{config.aria2_rpc_token}',
            [url],
            {
                'out': file_name
            }
        ]
    }
    response = requests.post(config.aria2_rpc_url, json=json_rpc_data)
    if response.status_code == 200:
        print('下载任务添加成功:', response.json())
        taskid = response.json()['result']
    else:
        print('添加任务失败:', response.status_code, response.text)
        raise '添加任务失败'
    time.sleep(10)

    json_rpc_data = {
        'jsonrpc': '2.0',
        'method': 'aria2.tellStatus',
        'id': 'qwer',
        'params': [
            f'token:{config.aria2_rpc_token}',
            taskid
        ]
    }
    i_time = 0
    low_speed_time = 0
    while i_time < 720:
        time.sleep(5)
        response = requests.post(config.aria2_rpc_url, json=json_rpc_data)
        task_info = response.json().get('result', {})
        status = task_info.get('status')
        if status == 'active':
            download_speed = task_info.get('downloadSpeed', '0')
            download_speed_kbps = int(download_speed) / 1024
            if download_speed_kbps < 50:
                low_speed_time += 1
                if low_speed_time > 12:
                    print(download_speed_kbps, 'kbps')
                    raise '下载速度过慢'
        elif status == 'complete':
            total_length = int(task_info.get('totalLength', 0))
            if total_length > 10240:
                print('下载完成')
                break
            else:
                if checkout > 0:
                    raise '下载失败1kb'
                else:
                    json_rpc_data = {
                        'jsonrpc': '2.0',
                        'method': 'aria2.removeDownloadResult',
                        'id': 'qwer',
                        'params': [
                            f'token:{config.aria2_rpc_token}',
                            taskid
                        ]
                    }
                    response = requests.post(config.aria2_rpc_url, json=json_rpc_data)
                    time.sleep(10)
                    download_aria2(url, file_name, checkout=1)
        else:
            print('下载状态：', status)
            raise '未知下载状态'
        i_time += 0


se = requests.session()

tagTrans = EhTagTranslation()

conn = config.conn
c = conn.cursor()

sqlstr = 'SELECT * FROM manga WHERE autostate = 6 ORDER BY timestamp DESC;'
c.execute(sqlstr)
mangaList = c.fetchall()
lense = len(mangaList)
dev = 0
i = 0
errorflag = 0
proxy = config.proxies0
while i < lense:
    proxy = config.proxyPool[dev % len(config.proxyPool)]
    manga = mangaList[i]
    print(str(i + 1) + '/' + str(lense))
    url = manga[2]
    try:
        data = se.get(url, headers=config.header, cookies=config.cookies2, proxies=proxy).text
        info = parseinfo(data)
    except:
        print('error', url, proxy)
        # print(data)
        errorflag += 1
        dev += 1
        if errorflag >= 5:
            raise 'error'
        else:
            time.sleep(2)
            continue
    errorflag = 0
    id = manga[0]
    name = html.unescape(info[0]).replace('"', '""')
    realname = getRealname(name)
    filename = manga[15]
    updatetime = time.time()
    tag_tran = tagTrans.getTrans(info[11])

    sqlstr = 'SELECT * FROM mangainfo WHERE id = "%s"' % (manga[0])
    c.execute(sqlstr)
    res = c.fetchall()
    if res:
        sqlstr = 'DELETE FROM mangainfo WHERE id = "%s"' % (manga[0])
        c.execute(sqlstr)
        print('updateinfo' + manga[0])

    sqlstr = 'INSERT INTO mangainfo (id,name,romaname,realname,link,category,uploader,postedtime,language,estimatedsize,pages,favorited,ratingcount,rating,updatetime,state,tag,tagtran)values("%s","%s","%s","%s","%s","%s","%s","%s","%s","%s",%d,%d,%d,%d,%d,%d,"%s","%s");' \
             % (id, name, info[1], realname, url, info[2], info[3], info[4], info[5], info[6], info[7], info[8],
                info[9], info[10], updatetime, 1, info[11], tag_tran)
    print('insert mangainfo:', manga[0], manga[1])
    try:
        c.execute(sqlstr)
    except Exception as e:
        print('insert mangainfo error', manga[0], manga[1])
        print(e)
        print(sqlstr)
        raise 'insert mangainfo error'

    downloadlink = info[12]
    downpage = se.get(info[12], headers=config.header, cookies=config.cookies2, proxies=proxy).text
    soup2 = BeautifulSoup(downpage, 'lxml')
    direct_cost = soup2.find("div", style="width:180px; float:left").find("div",
                                                                          style="text-align:center; margin-top:4px").find(
        "strong").text
    if direct_cost == 'Free!':
        direct_cost = 0
    else:
        direct_cost = int(direct_cost[:-3].replace(',', ''))
    for td in soup2.find_all('td'):
        p_tags = td.find_all('p')
        if p_tags and p_tags[0].text.strip() == 'Original':
            target_td = td
            break
    hah_cost = target_td.find_all('p')[2].text
    if hah_cost == 'Free':
        hah_cost = 0
    else:
        hah_cost = int(hah_cost[:-3].replace(',', ''))

    downflag = 0
    if direct_cost == 0 or direct_cost < hah_cost or hah_cost > 8000 or hah_cost < 400:
        downflag = 1

    postlink = info[12].replace('--', '-')
    if downflag == 0:
        print('hah download')
        req2 = se.post(postlink, headers=config.header, cookies=config.cookies2, data={'hathdl_xres': 'org'},
                       proxies=proxy).text
        if 'An original resolution download has been queued for client' not in req2:
            print(postlink)
            print(req2)
            raise 'hah post error'

        timestamp = int(time.time())
        sqlstr = 'UPDATE manga SET autostate = 7 ,remark="%s" WHERE id = "%s"' % (timestamp, manga[0])
        c.execute(sqlstr)
        conn.commit()

    else:
        print('direct download')
        print(manga[0])
        data = se.post(postlink, headers=config.header, cookies=config.cookies2,
                       data={'dltype': 'org', 'dlcheck': 'Download Original Archive'}, proxies=proxy).text
        # print(data)
        soup3 = BeautifulSoup(data, 'lxml')
        templink = soup3.find("p", id="continue").find('a')['href']
        downlink = templink + '?start=1'
        idname = '[' + manga[0].split('/')[0] + ']'
        if idname in config.too_long_name_list:
            zipname = config.too_long_name_list[idname]
        else:
            zipname = '[' + manga[0].split('/')[0] + ']' + re.sub(r'[\\/*?:"<>|]', '_', name) + '.zip'
        print(downlink)
        print(zipname)
        download_aria2(downlink, zipname)
        sqlstr = 'UPDATE manga SET autostate = 11 ,filename="%s" WHERE id = "%s"' % (zipname, manga[0])
        c.execute(sqlstr)
        conn.commit()

    if info[13] != 'None':
        sqlstr = f'SELECT * FROM manga WHERE id LIKE "{info[13]}/%";'
        c.execute(sqlstr)
        res = c.fetchall()
        if res:
            sqlstr = 'UPDATE manga SET state = -1 WHERE id = "%s"' % (res[0][0])
            print(sqlstr)
            c.execute(sqlstr)
            conn.commit()

    today = datetime.date.today()
    year, week, _ = today.isocalendar()
    weeknum = year * 100 + week
    sqlstr = f'SELECT * FROM GP WHERE week={weeknum}'
    c.execute(sqlstr)
    req = c.fetchall()
    if not req:
        gpreq = se.get('https://e-hentai.org/exchange.php?t=gp', headers=config.header, cookies=config.cookies2,
                       proxies=proxy).text
        gpstr = re.search('Available: (.*?) kGP', gpreq)[1]
        gp = int(gpstr.replace(',', '')) * 1000
        print(gp)
        sqlstr = f'UPDATE GP SET nowgp={gp} WHERE week={weeknum - 1};'
        c.execute(sqlstr)
        sqlstr = f'INSERT INTO GP (week,quota)values({weeknum},"{info[10]} MiB");'
        c.execute(sqlstr)
        conn.commit()
    else:
        file_sizes = [req[0][1], info[6]]
        total_size = sum(parse_file_size(size) for size in file_sizes)
        total_size_mb = str(int(total_size / (1024 ** 2))) + ' MiB'
        sqlstr = f'UPDATE GP SET quota="{total_size_mb}" WHERE week={weeknum};'
        c.execute(sqlstr)
        conn.commit()

    print(manga[0], manga[1])
    i += 1

    if i < lense:
        time.sleep(20 + random.randint(0, 40))
        if downflag == 0:
            i_time = 0
            partial_name = '[' + manga[0].split('/')[0] + ']'
            while i_time < 80:
                time.sleep(20)
                flag = check_complete(config.hah_download_path, partial_name)
                if flag[0] == True:
                    sqlstr = f'UPDATE manga set state = 10, alias="{flag[1]}" WHERE state = 9 and id="{manga[0]}";'
                    print('completeHah', manga[0], manga[1])
                    c.execute(sqlstr)
                    conn.commit()
                    break
                i_time += 1

print('done')
