# KwikiPageSync

## 說明
* 此為用作同步Reko Wiki (https://rekowiki.tk/wiki/index.php) 和 Fandom K wiki (https://newkomica-kari.fandom.com/zh-tw/wiki/%E9%A6%96%E9%A0%81) 頁面的腳本
* 此腳本會檢查兩邊wiki的更新時間，以最遲更新時間為準，覆寫較早的更新時間的內容
    * 例如條目在Reko時12:00出現更新，那Reko和Fandom的條目都會以12:00更新的版本為準，並把Fandom上的內容以Reko的內容覆寫
    * 更新後會加上模板{{synchro}}，通知用戶檢查更新內容會否覆蓋掉自己的編輯
* 留意：
    * 此腳本暫只能同步正常頁面，不建議用作同步模版、分頁、或是檔案等特殊頁面
    * 此腳本暫不能處理頁面易名的情況，請自己手動處理
    * 如頁面中有檔案，此腳本不能同時更新頁面中的檔案

## 必備條件
* Python 3.6+    
    * Windows可參照此URL安裝：https://learn.microsoft.com/zh-tw/windows/python/beginners
    * Linux系OS應是預先安裝，如不是請跟據OS本身的程式庫安裝(如使用apt-get)
    * Max OS系請自行找方法，作者沒錢沒肝沒腎買蘋果
    * 安裝後，在命令提示字元 (Command Prompt) 中打入 "python --version" (或"python3 --version") 會出現 "Python 3.x.x"
* 註冊機械人用戶    
    * Reko Wiki：https://rekowiki.tk/wiki/index.php/%E7%89%B9%E6%AE%8A:BotPasswords
    * Fandom K wiki：https://newkomica-kari.fandom.com/zh-tw/wiki/%E7%89%B9%E6%AE%8A:BotPasswords
    * 要求權限：
        * 大量編輯
        * 匯入修訂版本
        * 編輯現有的頁面
        * 編輯受保護的頁面
        * 建立、編輯與移動頁面
        * 上傳新檔案	
        * 上傳、取代與移動檔案

## 使用文法
* 設定 config.json
    * 複製 config.sample.json 到 config.json
    * config.json 一定要和腳本中的sync_page.py放在同一個資料夾中
    * 修改 config.json 中的資料       
        * 設定Reko Wiki 機械人用戶資料
        ```
        "reko": {
            ...
            "botName": "<你的機械人用戶名稱>",
            "botPassword": "<你的機械人用戶密碼>"
        },
        ```
        * 設定Fandom K wiki 機械人用戶資料
        ```
        "fandom": {
            ...
            "botName": "<你的機械人用戶名稱>",
            "botPassword": "<你的機械人用戶密碼>"
        },
        ```
        * 設定需要同步的頁面名稱，可多於一頁
        ```
        "pages": [
            "カードファイト!! ヴァンガード overDress",
            ...            
        ]
        ```
* 在命令提示字元 (Command Prompt)中，移到腳本中sync_page.py所在的資料夾
```
cd C:\<資料夾位置>
```
* 在命令提示字元 (Command Prompt)中，用python運行腳本 (留意：所使用的指令不一定是python，有可能是python3或是python3.x，請等參照自己的OS環境)
```
python sync_page.py
```
* 如成功執行，會出現以下訊息
```
同步: ['Reko Wiki', 'New Komica wiki (仮)']
同步頁面： カードファイト!! ヴァンガード overDress
頁面同步到reko成功!
...
```

