import json

class EhTagTranslation():
    def __init__(self,path=r'./db.text.json'):
        with open(path, 'r', encoding='utf-8') as fcc_file:
            self.dbtext = json.load(fcc_file)['data']
            self.dbindex={
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
            self.rows={}
            for i in self.dbtext[0]['data']:
                self.rows[i]=self.dbtext[0]['data'][i]['name']

    def getTrans(self,string):
        tagList=[]
        for tag_raw in string.split(','):
            row, tag = tag_raw.split(':')
            row_t=self.rows[row]
            try:
                tag_t=self.dbtext[self.dbindex[row]]['data'][tag]['name']
            except KeyError:
                tag_t=tag
            tagList.append(row_t+':'+tag_t)
        return ','.join(tagList)



