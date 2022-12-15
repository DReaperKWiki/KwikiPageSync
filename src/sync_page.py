
import json
import requests
from datetime import datetime

def answer(equation):
    x = 0
    if '+' in equation:
        y = equation.split('+')
        x = int(y[0])+int(y[1])
    elif '−' in equation:
        y = equation.split('−')
        x = int(y[0])-int(y[1])
    return x

class WikiSync():

    def __init__ (self, source, targets):
        self.source = source
        self.targets = targets

    def sync_page(self, title):
        srcCode, time = self.query_page(title)  
        if srcCode is None:
            print("錯誤！找不到頁面{}!".format(title))
            return
        if srcCode.lower().find("{{mirrorpage}}") >= 0:
            print("錯誤！{}為鏡面頁面!".format(title))
            return
        srcCode = self.edit_src(srcCode)
        for key in self.targets:
            update_suc, res = self.post_edit(self.targets[key], title, srcCode, time=time)
            if update_suc:
                print("頁面同步到{}成功!".format(key))
            elif type(res) == str:
                print("頁面同步到{}失敗:".format(key), res)
            else:
                print("頁面同步到{}失敗:".format(key), res.status_code, res.text)

    def query_page(self, title, url=None):
        if not url:
            url = self.source["url"]
        response = requests.get(
            url,
            params={
                'action': 'query',
                'format': 'json',
                'titles': title,
                'prop': 'revisions',
                'rvprop': 'content|timestamp'
            }
        ).json()
        if '-1' in response['query']['pages']:
            return None
        page = next(iter(response['query']['pages'].values()))
        wikicode = page['revisions'][0]['*']
        timestr = page['revisions'][0]['timestamp']
        # remove the trailing z
        time = datetime.fromisoformat(timestr[0:-1])
        return wikicode, time

    def edit_src(self, srcCode):
        lines = srcCode.split('\n')
        found = False
        for idx in range(0, len(lines)):
            if lines[idx].lower().find("{{h0") >= 0:
                lines.insert(idx+1, "{{mirrorpage}}")
                found = True
                break
        if not found:
            lines.insert(0, "{{mirrorpage}}")
        return ('\n'.join(lines))
    
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
    
    def post_edit(self, target, title, srcCode, time=None):
        if time != None and target.get('skipNewer'):
            targetCode, targetTime = self.query_page(
                title, url=target["url"]
            )
            if targetTime > time:
                suc = False
                msg = 'skip-newer: %s on %s (%s) is newer than source (%s)' % (
                    title, target['url'], targetTime, time
                )
                return suc, msg

        sess = requests.Session()
        # Get Request to fetch login token
        para = {
            "action": "query",
            "meta": "tokens",
            "type": "login",
            "format": "json"
        }
        res = sess.get(url=target["url"], params=para)
        data = res.json()
        tokens = data['query']['tokens']['logintoken']
        # Send a post request to login.
        para = {
            "action": "login",
            'lgname': target["botName"],
            'lgpassword': target["botPassword"],
            "lgtoken": tokens,
            "format": "json"
        }
        res = sess.post(url=target["url"], data=para)
        # GET request to fetch CSRF token
        para = {
            "action": "query",
            "meta": "tokens",
            "format": "json"
        }
        res = sess.get(url=target["url"], params=para)
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
        res = sess.post(url=target["url"], data=para)
        # check if captcha is needed
        suc, data = self.check_success(res)
        if not suc:
            if "edit" in data and "captcha" in data["edit"]:
                captcha_id = data["edit"]["captcha"]["id"]
                captcha_q = data["edit"]["captcha"]["question"]
                ans = answer(captcha_q)
                para["captchaword"] = str(ans)
                para["captchaid"] = captcha_id
                res = sess.post(url=target["url"], data=para)
                suc, data = self.check_success(res)
        return suc, res


if __name__ == "__main__":
    # read config
    data = {}
    with open("config.json", "r") as jsonfile:
        data = json.load(jsonfile)    

    if ("pages" not in data) or (len(data["pages"]) == 0):
        print("設定錯誤: 沒有頁面設定")
        quit()

    if "source" not in data:
        print("設定錯誤: 沒有來源")
        quit()

    if "target" not in data:
        print("設定錯誤: 沒有目的地")
        quit()
    
    source_key = data["source"]
    target_keys = data["target"]

    if source_key not in ("reko", "fandom"):
        print("設定錯誤: 來源應是'reko'或是'fandom'")
        quit()

    if len([en for en in target_keys if en not in ("reko", "fandom")]) > 0:
        print("設定錯誤: 目的地應是'reko'或是'fandom'")
        quit()

    if source_key in target_keys:
        print("設定錯誤: 來源不應包含在目的地之中")
        quit()

    if data["source"] not in data:
        print("設定錯誤: 沒有設定來源 {}".format(data["source"]))
        quit()
    
    for en in data["target"]:
        if en not in data:
            print("設定錯誤: 沒有設定目的地 {}".format(en))
            quit()

    source = data[data["source"]]
    targets = { en:data[en] for en in data["target"] }

    print("同步", data["source"], "=>", data["target"])
    
    synchronizer = WikiSync(source, targets)
    
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

