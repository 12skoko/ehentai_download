''''''
"""manga
-4:推送raragi出错
-3:种子下载出错
-2:档案过时已删除
-1:档案过时
0：已完成
1：仅添加
2：待下载种子
3：不下载（已有汉化）
4：不下载（其他原因）
5：已下载种子
6：无seed
7：已完成种子
8：已推送info
9：已下载文件
10：已完成下载
11:直接下载
12：已压缩（hah
13:优先下载
14：已下载（优先
15：无seed（优先
"""


"""manga_autostate
-5：推送raragi出错
-4：压缩出错
-3：种子下载出错
-2：档案过时
-1:未满12小时
0：已完成
1：仅添加
2：待下载种子
3：不下载
4：已推送torrent
5：torrent下载完成
6：无seed,需要hah下载
7：已推送hah下载
8：torrent已获取info
9：hah下载完成
10：hah压缩完成
11：直接下载



"""


"""manga-info
-1:未定义出错
0：已完成
1：仅添加
2：已收集
3：无法收集
"""

"""
CREATE TABLE "manga" (
	"id"	TEXT NOT NULL UNIQUE,
	"name"	TEXT NOT NULL,
	"link"	TEXT NOT NULL,
	"torrentlink"	TEXT,
	"time"	TEXT,
	"type"	TEXT,
	"tag"	TEXT,
	"pages"	INTEGER,
	"rating"	INTEGER,
	"state"	INTEGER NOT NULL,
	"relatetation"	INTEGER,
	"remark"	TEXT,
	"realname"	TEXT,
	"alias"	TEXT,
	"filename"	TEXT
);
"""