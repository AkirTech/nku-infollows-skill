# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About

- This is a skill for claude code. In `src\main` lies a standard structure of a skill.
- This project aims at creating a more convenient experience that allows user to keep up with the most valuable news on WeChat subscriptions.

## Architecture

- use `wechat-download-api` to get wechat articles.(Python 3.8+ with FastAPI)(Refer to `Reference` part of this file to see more).
- create a temp dir. For saving each article, you can either *seek method after researching how the wechat-download-api implements the functions in their HTMLs and use native Python to access them* or just *request the backend to upgrade articles and access them through sqlite(database in `src\backend\wechat-download-api\data\rss.db`)*

### Two modes
- Single:
    - Check if the backend is running.
    - Check if the subscription list is not empty.
    - Fetch articles (backend). Pay attention to rate limit!(Refer to file `src\backend\wechat-download-api\.env`)
    - Export the articles as json schema and save:(directly select from database after fetch `id` `title` `link` `author`)
    ```json
    {
        "id":int,
        "title":string,
        "link":string,
        "author":string,
        "keywords":string
    }
    ```
    (Note: keywords are not contained in database, but rather, you need to generate some words basing on your conprehension to the title and the author name)
    - Example:
    ```json
    {
        "id":5,
        "title":"南开大学发布暑假放假通知！",
        "link":"https://mp.weixin.qq.com/s/XxwJo1ueMSvOaTXOs-DHdg",
        "author":"南开大学",
        "keywords":"假期 | 重要通知"
    }
     ```
    - Create a standalone model html file used to display the json. 
    - Sort and filter the content of json file and record the most valuable items' id.
    - Generate recommendation html based on the recorded ids and dislay them in the html.
    - Defaultly open the html file with default browser.
- Loop:
    - from trigger the skill, do the process of `Single` every 1 hour.
    - **Remember to clear the previous recommendations data for saving storage.**
### Clear
- Clear generated json and 

## References

- An `openapi.json` file is saved in `.\refs\`, it contains api references of the backend server `wechat-download-api`.
- Attention to `.\src\backend\wechat-download-api\README.md` is needed.
- You may also refer to scripts in html files in `src\backend\wechat-download-api\static` to learn how to invoke apis.
- The database contains sheets including `articles` and `subscriptions`.
- Structure of articles: (in the quotes lies my research)
---
||||||||||||||
|--|--|--|--|--|--|--|--|--|--|--|--|--|
|id|fakeid|aid|title|link|digest|cover|author|content|plain_content|publish_time|fetched_at|source|
|(the order)|(identity of the wechat subscription account)|(?)|(title of article)|(article link)|(?)|(article cover)|(author)|(HTML like content)|(text only content)|(publish time)|(fetch time)|(auto generated)|
||||||||||||||

- `src\backend\wechat-download-api\data\.credentials.json` lies the credential of the current user (wechat requires an account logged in to access other articles.)

- Use the MCP service provided by backend if it's ready.

## Note

- The core of the skill is not just fetch articles but emphasizes "Recommend" more.