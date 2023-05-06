import re
import json
import requests
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

    def query_recent_changes(self, target_date):
        response = requests.get(
            self.info["url"],
            params={
                'action': 'query',
                'format': 'json',
                'list': 'recentchanges',
                'rcstart': target_date.strftime("%Y-%m-%d") + 'T23:59:00Z', # why inverted?
                'rcend': target_date.strftime("%Y-%m-%d") + 'T00:00:00Z',    # why inverted?
                'rcprop': 'title|timestamp|user|comment',
                'rclimit': 500,
                'rctype': 'edit|new',
                'rcdir': 'older'
            }
        ).json()
        return response['query']['recentchanges']

    def query_page(self, title):
        response = requests.get(
            self.info["url"],
            params={
                'action': 'query',
                'format': 'json',
                'titles': title,
                'prop': 'revisions',
                'rvprop': 'timestamp|user|content|comment'
            }
        ).json()
        if '-1' in response['query']['pages']:
            return None
        page = next(iter(response['query']['pages'].values()))
        return page['revisions'][0]
    
    def check_success(self, res):
        data = res.json()
        if res.status_code != 200:
            return False, data
        if "edit" not in data:
            return False, data
        if "result" not in data["edit"]:
            return False, data
        if data["edit"]["result"] != "Success":
            return False, data
        return True, data
        
    def post_edit(self, title, srcCode, autobot_comment):
        # GET request to fetch CSRF token
        para = {
            "action": "query",
            "meta": "tokens",
            "format": "json"
        }
        res = self.sess.get(url=self.info["url"], params=para)
        data = res.json()
        csrf_tokens = data['query']['tokens']['csrftoken']
        # POST request to edit a page
        para = {
            "action": "edit",
            "title": title,
            "token": csrf_tokens,
            "format": "json",
            "text": srcCode,
            "watchlist": "unwatch",
            "summary": autobot_comment, 
            "bot": True
        }
        res = self.sess.post(url=self.info["url"], data=para)
        # check if captcha is needed
        suc, data = self.check_success(res)
        if not suc:
            if "captcha" in data["edit"]:
                captcha_id = data["edit"]["captcha"]["id"]
                captcha_q = data["edit"]["captcha"]["question"]
                ans = answer(captcha_q)
                para["captchaword"] = str(ans)
                para["captchaid"] = captcha_id
                res = self.sess.post(url=self.info["url"], data=para)
                suc, data = self.check_success(res)
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

    def get_recent_change(self):
        recent_update = {}
        # note: need to sort the list based on updated date time
        with open_editor(self.wikis) as editors:
            for key in editors:
                # print(key) 
                lst = editors[key].query_recent_changes(datetime.date.today() + datetime.timedelta(days = -1))
                for en in lst:
                    if en["comment"] != WikiSync.AUTOBOT_COMMENT: # ignore auto update
                        if en["title"] not in recent_update:
                            recent_update[en["title"]] = en["timestamp"]
                        else:
                            recent_update[en["title"]] = max(en["timestamp"], recent_update[en["title"]])
        lst = [ [ recent_update[key], key ] for key in recent_update ]
        lst = sorted(lst)
        return [ en[1] for en in lst ]
    
    def sync_all_pages(self, cur_list):
        with open_editor(self.wikis) as editors:
            for title in cur_list:
                try:
                    self.sync_page(editors, title)
                except Exception as e:
                    self.logger.error("頁面{}同步失敗:{}".format(title, str(e)))
                time.sleep(1) # wait one second to avoid massive edit

    # sync page:
    # 1) check latest revision of all wiki site
    # 2) compare update time stamp, select the one with latest timestamp and longest text
    # 3) update all sites using the one with latest timestamp 
    def sync_page(self, editors, title):
        # user = page['revisions'][0]['user']
        # ts = page['revisions'][0]['timestamp']
        # comment = page['revisions'][0]['comment']
        # wikicode = page['revisions'][0]['*']
        all_revision = {}
        for key in editors:
            all_revision[key] = editors[key].query_page(title)
        if len([key for key in all_revision if all_revision[key] is not None]) == 0:
            self.logger.error("錯誤！找不到頁面{}!".format(title))
            return
        # get latest revision
        def func(key):
            if all_revision[key] is None:
                return "1900-01-01T00:00:00Z"
            return all_revision[key]['timestamp']
        latest_rev = max(all_revision, key=func)
        # if the latest update is from wikibot, ignore
        if all_revision[latest_rev]["comment"] == WikiSync.AUTOBOT_COMMENT:
            self.logger.error("頁面{}經已同步".format(title))
            return
        wikicode = all_revision[latest_rev]['*']
        # edit source
        wikicode = self.edit_src(wikicode, title)
        # sync to other wikis
        for key in editors:
            if key == latest_rev:
                continue
            if all_revision[key] is None:
                update_suc, res = editors[key].post_edit(title, wikicode, WikiSync.AUTOBOT_COMMENT)
            else:
                self.wikis[key], all_revision[key], all_revision[latest_rev]
                newcode = self.compare_src({
                    "src_wiki_name": self.wikis[latest_rev]["name"],
                    "src_wiki_update": all_revision[latest_rev]["timestamp"],
                    "target_wiki_content": all_revision[key]["*"],
                },wikicode, title)
                if newcode is not None:
                    update_suc, res = editors[key].post_edit(title, newcode, WikiSync.AUTOBOT_COMMENT)
                else:
                    update_suc = True
            if update_suc:
                self.logger.info("頁面{}同步到{}成功!".format(title, key))
            else:
                self.logger.info("頁面{}同步到{}失敗: {} {}".format(title, key, res.status_code, res.text))
    
    def edit_src(self, srcCode, title):
        # change fandom-table to wikitable
        srcCode = srcCode.replace("fandom-table", "wikitable")
        # remove {{mirrorpage}} template
        # remove {{synchronized|<wiki name>|<timestamp>}} template
        srcCode = self.remove_template(srcCode, ["mirrorpage", r"synchro\|[^\}]*"], title.startswith("模板:"))
        return srcCode
    
    def compare_src(self, info, newCode, title):
        oldCode = info["target_wiki_content"]
        oldCode = self.edit_src(oldCode, title)
        # remove all space and new lines and check for changes
        oldCodeRaw = re.sub(r"\n|\s", "", oldCode).lower()
        newCodeRaw = re.sub(r"\n|\s", "", newCode).lower()
        # if it is the same, no need to update
        if newCodeRaw == oldCodeRaw:
           return None
        # else insert template       
        dt = time.strptime(info['src_wiki_update'], '%Y-%m-%dT%H:%M:%SZ')
        dt = calendar.timegm(dt)
        dt = datetime.datetime.fromtimestamp(dt)
        # print("timestamp", dt, info['src_wiki_update'])
        newtmpl = "{{synchro|" + info["src_wiki_name"] + "|" + dt.strftime("%Y年%m月%d日 %H:%M") + "}}"
        newCode = self.insert_template(newCode, newtmpl, title.startswith("模板:"))
        # replace too many new lines
        newCode = re.sub(r"\n\n\n[\n]*", "\n\n", newCode)
        return newCode

    def remove_template(self, srcCode, templates, is_template):
        lines = srcCode.split('\n')
        for idx in range(0, len(lines)):
            for tm in templates:
                if is_template:
                    lines[idx] = re.sub(r"\<noinclude\>\{\{" + tm + r"\}\}\<\/noinclude\>", "", lines[idx])
                else:
                    lines[idx] = re.sub(r"\{\{" + tm + r"\}\}", "", lines[idx])
        return ('\n'.join(lines))

    def insert_template(self, srcCode, template, is_template):
        if is_template:
            template = "<noinclude>" + template + "</noinclude>"
        lines = srcCode.split('\n')
        # for redirected page, place the template at the bottom, otherwises the wiki will think it is just a normal page
        if srcCode.startswith("#重新導向") or srcCode.startswith("#REDIRECT") or srcCode.startswith("#重定向"):
            lines.append(template)
        else:            
            found = False
            for idx in range(0, len(lines)):
                if lines[idx].lower().find("{{h0") >= 0:
                    lines.insert(idx+1, template)
                    found = True
                    break
            if not found:
                lines.insert(0, template)
        return ('\n'.join(lines))


if __name__ == "__main__":
    logger = logging.getLogger('wiki')

    # read config
    data = {}
    with open("config.json", "r", encoding="utf-8") as jsonfile:
        data = json.load(jsonfile)    

    if (("pages" in data) and (len(data["pages"]) == 0)):
        logger.error("設定錯誤: 沒有頁面設定")
        quit()

    if ("wiki" not in data) or (len(data["wiki"]) == 0):
        logger.error("設定錯誤: 沒有源頭")
        quit()

    logger.info("同步: {}".format(str([ data["wiki"][key]["name"] for key in data["wiki"] ])))
    
    synchronizer = WikiSync(data["wiki"], logger)

    if "pages" not in data:
        logger.info("起動自動化同步模式")
        cur_list = synchronizer.get_recent_change()
        data["pages"] = cur_list

    # remove page not to be sync
    cur_list = []
    for en in data["pages"]:
        can_sync = True
        for prefix in WikiSync.NON_SYNC_PREFFIX:
            if en.startswith(prefix):
                logger.error("錯誤:不能同步{} - {}".format(WikiSync.NON_SYNC_PREFFIX[prefix], en))
                can_sync = False
                break
        if can_sync:
            cur_list.append(en)
    
    synchronizer.sync_all_pages(cur_list)
