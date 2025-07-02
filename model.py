from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger

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
