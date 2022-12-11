
import json
import requests

class WikiSync():

    def __init__ (self, source, targets):
        self.source = source
        self.targets = targets

    def sync_page(self, title):
        srcCode = self.query_page(title)  
        if srcCode.lower().find("{{mirrorpage}}") >= 0:
            print("錯誤！{}為鏡面頁面!".format(title))
            return
        srcCode = self.edit_src(srcCode)
        for key in self.targets:
            res = self.post_edit(self.targets[key], title, srcCode)
            if res.status_code == 200:
                print("頁面同步到{}成功!".format(key))
            else:
                print("頁面同步到{}失敗:".format(key), res.status_code, res.text)

    def query_page(self, title):
        response = requests.get(
            self.source["url"],
            params={
                'action': 'query',
                'format': 'json',
                'titles': title,
                'prop': 'revisions',
                'rvprop': 'content'
            }
        ).json()
        page = next(iter(response['query']['pages'].values()))
        wikicode = page['revisions'][0]['*']
        return wikicode

    def edit_src(self, srcCode):        
        lines = srcCode.split('\n')
        for idx in range(0, len(lines)):            
            if lines[idx].lower().find("{{h0") >= 0:                
                lines.insert(idx+1, "{{mirrorpage}}")
                break
        return ('\n'.join(lines))
    
    def post_edit(self, target, title, srcCode):
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
        return res


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
        else:
            print("同步頁面：", en)
            synchronizer.sync_page(en)

