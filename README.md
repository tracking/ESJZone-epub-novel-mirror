# ESJZone 的简中小说EPUB全部备份

从项目 [/ZALin/ESJZone-novel-mirror/](https://github.com/ZALin/ESJZone-novel-mirror/tree/main) 修改而来

包含原项目已经备份小说

### 备份说明
1. 包含图片，超链接文本。并且尝试分析目录。不备份文字css样式
2. 原项目小说备份位于Novel文件夹下。本项目备份epub小说位于/epubBooks_esjzone。新txt备份位于/txtBooks_esjzone
3. 不备份备份时间已经已经下架小说，密码页面跳过

### 手动更新使用方法
1. 确保你拥有基本的python知识和命令行使用方法
2. 命令行执行 pip install beautifulsoup4 ebooklib opencc requests
3. 打开py文件。更改位于开头参数
- 繁简转换。
  - 默认为繁体转简体。如需要简体转繁体将`converter = opencc.OpenCC('t2s.json')`里的`t2s.json`改为`s2t.json`
- 小说下载
  - 若需要下载单本小说。使`isDownloadAll = False`。然后更改`bookURL`变量值。网址包含detail，类似于`https://www.esjzone.cc/detail/1557379934.html`
  - 若需要备份全部小说或某一类别全部小说。使`isDownloadAll = True`。然后更改`bookListURL`变量值。应包含tag或list。类似于`https://www.esjzone.cc/list-04/`或 `https://www.esjzone.cc/tags/R18/`
- Cookie设置
  - 部分书籍需要设置cookie打开浏览器，登录esjzone。自行搜索浏览器cookie复制方法。复制`ews_key` `ews_key`两个cookie变量，填入变量`cookie`中。使其看起来类似于
    ```
    cookie = "ews_key=AAAAAAAAAAAAAAAA; " \
         "ews_token=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB;"
    ```
  - 线程下载数
    - 默认为4。想要下载快一些可以调大。不建议调太大防止引发站点反爬虫机制

### 项目fork时间
2024/02/03
### 项目更新时间
