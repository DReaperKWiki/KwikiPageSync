import re
import os
import io
import json
import requests
import base64
import contextlib
import datetime
import calendar
import time
import logging


FORMAT = '%(asctime)s: %(message)s'
logging.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO,  handlers=[
    logging.FileHandler("auto_sync.log", encoding = "UTF-8"),
    logging.StreamHandler()
])

def answer(equation):
    x = 0
    if '+' in equation:
        y = equation.split('+')
        x = int(y[0])+int(y[1])
    elif '−' in equation:
        y = equation.split('−')
        x = int(y[0])-int(y[1])
    return x

@contextlib.contextmanager
def open_editor(wikis):
    editors = { key:WikiEditor(wikis[key]) for key in wikis }
    for key in editors:
        editors[key].login()
    yield editors
    for key in editors:
        editors[key].logout()


class WikiEditor(object):

    def __init__ (self, info):
        self.info = info
        self.sess = None
    
    def login(self):
        self.sess = requests.Session()
        # Get Request to fetch login token
        para = {
            "action": "query",
            "meta": "tokens",
            "type": "login",
            "format": "json"
        }
        res = self.sess.get(url=self.info["url"], params=para)
        data = res.json()
        tokens = data['query']['tokens']['logintoken']
        # Send a post request to login.
        para = {
            "action": "login",
            'lgname': self.info["botName"],
            'lgpassword': self.info["botPassword"],
            "lgtoken": tokens,
            "format": "json"
        }
        res = self.sess.post(url=self.info["url"], data=para)

    def logout(self):
        # GET request to fetch CSRF token
        para = {
            "action": "query",
            "meta": "tokens",
            "format": "json"
        }
        res = self.sess.get(url=self.info["url"], params=para)
        data = res.json()
        csrf_tokens = data['query']['tokens']['csrftoken']
        # Send a post request to logout.
        para = {
            "action": "logout",
            "token": csrf_tokens,
        }
        res = self.sess.get(url=self.info["url"], params=para)
        self.sess = None

    def query_recent_upload(self, target_date):
        response = requests.get(
            self.info["url"],
            params={
                'action': 'query',
                'format': 'json',
                'list': 'allimages',
                'aistart': target_date.strftime("%Y-%m-%d") + 'T23:59:00Z', # why inverted?
                'aiend': target_date.strftime("%Y-%m-%d") + 'T00:00:00Z',    # why inverted?
                'aiprop': 'title|timestamp|user|comment|url',
                'ailimit': 500,
                'aidir': 'descending',
                'aisort': 'timestamp'
            }
        ).json()        
        return response['query']['allimages']
    
    def check_success(self, res, action):
        data = res.json()
        if res.status_code != 200:
            return False, data
        if action not in data:
            return False, data
        if "result" not in data[action]:
            return False, data
        if data[action]["result"] != "Success":
            return False, data
        return True, data

    def upload_file(self, title, file, autobot_comment):
        # GET request to fetch CSRF token
        para = {
            "action": "query",
            "meta": "tokens",
            "format": "json"
        }
        res = self.sess.get(url=self.info["url"], params=para)
        data = res.json()
        csrf_tokens = data['query']['tokens']['csrftoken']
        # POST request to upload image
        para = {
            "action": "upload",
            "filename": title,
            "token": csrf_tokens,
            "format": "json",
            "ignorewarnings": 1,
            "comment": autobot_comment            
        }
        u_file = {'file':(title, file, 'multipart/form-data')}
        res = self.sess.post(url=self.info["url"], files=u_file, data=para)
        # print(res)
        suc, data = self.check_success(res, "upload")
        return suc, res


class WikiSync():

    NON_SYNC_PREFFIX = {
        "首頁":"首頁",
        "檔案":"檔案",
        "使用者": "使用者專頁",
        "特殊":"特殊分頁",
        "討論:":"討論分頁",
        "模板:Mirrorpage":"模板:Mirrorpage",
        "模板:Synchro":"模板:Synchro" 
    }

    AUTOBOT_COMMENT = "Wiki-Bot 同步更新"

    def __init__ (self, wiki, logger):
        self.wikis = wiki
        self.logger = logger

    def get_recent_upload(self):
        page_info = {}
        recent_update = {}
        # note: need to sort the list based on updated date time
        with open_editor(self.wikis) as editors:            
            for key in editors:                
                page_info[key] = {}
                lst = editors[key].query_recent_upload(datetime.date.today() + datetime.timedelta(days = -1))
                for en in lst:
                    if en["comment"] != WikiSync.AUTOBOT_COMMENT: # ignore auto update                                                
                        page_info[key][en["title"]] = en
                        if en["title"] not in recent_update:
                            recent_update[en["title"]] = en["timestamp"]
                        else:                            
                            recent_update[en["title"]] = max(en["timestamp"], recent_update[en["title"]])
        lst = [ [ recent_update[key], key ] for key in recent_update ]
        lst = sorted(lst)        
        return [ en[1] for en in lst ], page_info
    
    def sync_all_images(self, cur_list, img_info):
        # print(cur_list)
        with open_editor(self.wikis) as editors:
            for title in cur_list:                
                try:
                    self.sync_image(editors, title, img_info)
                except Exception as e:
                    self.logger.error("{}同步失敗:{}".format(title, str(e)))
                time.sleep(1) # wait one second to avoid massive edit
    
    def sync_image(self, editors, title, img_info):        
        all_revision = {
            key: img_info[key][title] if title in img_info[key] else None for key in editors 
        }                    
        if len([key for key in all_revision if all_revision[key] is not None]) == 0:
            self.logger.error("錯誤！找不到{}!".format(title))
            return        
        # get latest revision
        def func(key):
            if all_revision[key] is None:
                return "1900-01-01T00:00:00Z"
            return all_revision[key]['timestamp']
        latest_rev = max(all_revision, key=func)
        # if the latest update is from wikibot, ignore
        if all_revision[latest_rev]["comment"] == WikiSync.AUTOBOT_COMMENT:
            self.logger.error("{}經已同步".format(title))
            return
        # download the files for checking
        img_file = {}
        source_file = None
        for key in editors:
            if all_revision[key] is None:
                img_file[key] = ""
            else:
                r = requests.get(all_revision[key]["url"])
                # content = io.BytesIO(r.content)
                img_file[key] = base64.b64encode(r.content).decode('ascii')
                if key == latest_rev:
                    source_file = io.BytesIO(r.content)
        if source_file is None:
            self.logger.info("{}同步失敗: file not found".format(title))
            return        
        for key in editors:
            if key == latest_rev:
                continue            
            if img_file[key] == img_file[latest_rev]:
                self.logger.info("{}經已同步!".format(title))
                continue
            # upload file to target
            update_suc, res = editors[key].upload_file(title, source_file, WikiSync.AUTOBOT_COMMENT)
            if update_suc:
                self.logger.info("{}同步到{}成功!".format(title, key))
            else:
                self.logger.info("{}同步到{}失敗: {} {}".format(title, key, res.status_code, res.text))


if __name__ == "__main__":
    logger = logging.getLogger('wiki')

    # read config
    data = {}
    with open("config.json", "r", encoding="utf-8") as jsonfile:
        data = json.load(jsonfile)    

    if ("wiki" not in data) or (len(data["wiki"]) == 0):
        logger.error("設定錯誤: 沒有源頭")
        quit()

    logger.info("同步: {}".format(str([ data["wiki"][key]["name"] for key in data["wiki"] ])))
    
    synchronizer = WikiSync(data["wiki"], logger)

    logger.info("檢查最近更新檔案")
    cur_list, img_info = synchronizer.get_recent_upload()

    synchronizer.sync_all_images(cur_list, img_info)
