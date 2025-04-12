import config

conn = config.createDBconn()
c = conn.cursor()

sqlstr='SELECT cid, name, realname FROM manga_picacg WHERE state = 1;'

c.execute(sqlstr)
res=c.fetchall()

i=1
lens=len(res)
for manga in res:
    print(str(i),'/',str(lens))


    sqlstr=f'SELECT id FROM mangainfo where realname="{manga[2]}";'

    c.execute(sqlstr)
    res2=c.fetchall()

    if manga[2] == 'こあくま学園レッスンライフ':
        print(sqlstr)
        print(res2)

    if res2 == ():
        # print(res2[0])
        sqlstr = f'UPDATE manga_picacg SET state=2 WHERE cid="{manga[0]}";'
        c.execute(sqlstr)
        print(sqlstr)

    i+=1


conn.commit()