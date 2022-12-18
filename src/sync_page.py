import re
import json
import requests
import contextlib
import datetime
import calendar
import time

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
        
    def post_edit(self, title, srcCode):
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
            "summary": "Wiki-Bot 同步更新", 
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

    def __init__ (self, wiki):
        self.wikis = wiki

    # TODO: sync page:
    # 1) check latest revision of all wiki site
    # 2) compare update time stamp, select the one with latest timestamp and longest text
    # 3) update all sites using the one with latest timestamp 
    def sync_page(self, title):
        # user = page['revisions'][0]['user']
        # ts = page['revisions'][0]['timestamp']
        # comment = page['revisions'][0]['comment']
        # wikicode = page['revisions'][0]['*']
        all_revision = {}
        with open_editor(self.wikis) as editors:
            for key in editors:
                all_revision[key] = editors[key].query_page(title)
        if len([key for key in all_revision if all_revision[key] is not None]) == 0:
            print("錯誤！找不到頁面{}!".format(title))
            return
        # get latest revision
        def func(key):
            if all_revision[key] is None:
                return "1900-01-01T00:00:00Z"
            return all_revision[key]['timestamp']
        latest_rev = max(all_revision, key=func)
        # if the latest update is from wikibot, ignore
        if all_revision[latest_rev]["comment"] == "Wiki-Bot 同步更新":
            print("頁面{}經已同步".format(title))
            return
        # edit source 
        wikicode = all_revision[latest_rev]['*']
        wikicode = self.edit_src(wikicode)
        # sync to other wikis
        with open_editor(self.wikis) as editors:
            for key in editors:
                if key == latest_rev:
                    continue
                if all_revision[key] is None:
                    update_suc, res = editors[key].post_edit(title, wikicode)
                else:
                    self.wikis[key], all_revision[key], all_revision[latest_rev]
                    newcode = self.compare_src({
                        "src_wiki_name": self.wikis[latest_rev]["name"],
                        "src_wiki_update": all_revision[latest_rev]["timestamp"],
                        "target_wiki_content": all_revision[key]["*"],
                    },wikicode)
                    if newcode is not None:
                        update_suc, res = editors[key].post_edit(title, newcode)
                    else:
                        update_suc = True
                if update_suc:
                    print("頁面同步到{}成功!".format(key))
                else:
                    print("頁面同步到{}失敗:".format(key), res.status_code, res.text)
    
    def edit_src(self, srcCode):
        # change fandom-table to wikitable
        srcCode = srcCode.replace("fandom-table", "wikitable")
        # remove {{mirrorpage}} template
        srcCode = self.remove_template(srcCode, ["mirrorpage", r"synchro\|[^\}]*"])
        # remove {{synchronized|<wiki name>|<timestamp>}} template
        return srcCode
    
    def compare_src(self, info, newCode):
        oldCode = info["target_wiki_content"]
        oldCode = self.edit_src(oldCode)
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
        newCode = self.insert_template(newCode, newtmpl)
        # replace too many new lines
        newCode = re.sub(r"\n\n\n[\n]*", "\n\n", newCode)
        return newCode

    def remove_template(self, srcCode, templates):
        lines = srcCode.split('\n')
        for idx in range(0, len(lines)):
            for tm in templates:
                lines[idx] = re.sub(r"\{\{" + tm + r"\}\}", "", lines[idx])
        return ('\n'.join(lines))

    def insert_template(self, srcCode, template):
        lines = srcCode.split('\n')
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
    # read config
    data = {}
    with open("config.json", "r") as jsonfile:
        data = json.load(jsonfile)    

    if ("pages" not in data) or (len(data["pages"]) == 0):
        print("設定錯誤: 沒有頁面設定")
        quit()

    if ("wiki" not in data) or (len(data["wiki"]) == 0):
        print("設定錯誤: 沒有源頭")
        quit()

    print("同步:", [ data["wiki"][key]["name"] for key in data["wiki"]])        
    
    synchronizer = WikiSync(data["wiki"])

    for en in data["pages"]:
        if en.startswith("首頁"):
            print("錯誤:不能同步首頁")
        elif en.startswith("檔案"):
            print("錯誤:不能同步檔案")
        elif en.startswith("使用者"):
            print("錯誤:不能同步使用者專頁")
        elif en.startswith("特殊"):
            print("錯誤:不能同步特殊分頁")
        elif en.startswith("模板"):
            print("錯誤:不能同步模板")
        else:
            print("同步頁面：", en)
            synchronizer.sync_page(en)

