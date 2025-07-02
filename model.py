from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger
import json

Base = declarative_base()


class Manga(Base):
    __tablename__ = "manga"

    manga_id = Column(String, primary_key=True)
    name = Column(String)
    link = Column(String)
    torrentlink = Column(String)
    postedtime = Column(DateTime)
    postedtimestamp = Column(Integer)

    state = Column(Integer)
    autostate = Column(Integer)
    filename = Column(String)
    torrenthash = Column(String)
    arcid = Column(String)
    remark = Column(String)

    realname = Column(String)
    category = Column(String)
    tag = Column(String)
    pages = Column(Integer)
    rating = Column(Integer)
    uploader = Column(String)
    alias = Column(String)

    relatetation = Column(BigInteger)
    fetchtime = Column(DateTime)


class MangaInfo(Base):
    __tablename__ = "mangainfo"

    manga_id = Column(String, primary_key=True)
    name = Column(String)
    romaname = Column(String)
    realname = Column(String)
    filename = Column(String)

    link = Column(String)
    category = Column(String)
    uploader = Column(String)
    postedtime = Column(DateTime)
    language = Column(String)
    estimatedsize = Column(String)
    pages = Column(Integer)
    favorited = Column(Integer)
    ratingcount = Column(Integer)
    rating = Column(Integer)

    fetchtime = Column(Integer)
    state = Column(Integer)

    tag = Column(String)
    tagtran = Column(String)

    remark = Column(String)


class EhTagTranslation():
    def __init__(self, path=r'./db.text.json'):
        with open(path, 'r', encoding='utf-8') as fcc_file:
            self.dbtext = json.load(fcc_file)['data']
            self.dbindex = {
                "rows": 0,
                "reclass": 1,
                "language": 2,
                "parody": 3,
                "character": 4,
                "group": 5,
                "artist": 6,
                "cosplayer": 7,
                "male": 8,
                "female": 9,
                "mixed": 10,
                "other": 11
            }
            self.rows = {}
            for i in self.dbtext[0]['data']:
                self.rows[i] = self.dbtext[0]['data'][i]['name']

    def get_trans(self, string):
        tag_list = []
        for tag_raw in string.split(','):
            row, tag = tag_raw.split(':')
            row_t = self.rows[row]
            try:
                tag_t = self.dbtext[self.dbindex[row]]['data'][tag]['name']
            except KeyError:
                tag_t = tag
            tag_list.append(row_t + ':' + tag_t)
        return ','.join(tag_list)
