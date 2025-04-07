# coding=utf-8
import bs4, hashlib, html, opencc, re, requests, sys, threading, uuid, retrying, os, gc, psutil
from datetime import datetime
from io import BytesIO
from os import path, mkdir
from time import sleep
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag, MarkupResemblesLocatorWarning
from ebooklib import epub
from requests import HTTPError
import warnings

# 记得更改参数 t2s是繁体转简体 s2t是简体转繁体
converter = opencc.OpenCC('t2s.json')
# 是否为全部下载
isDownloadAll = True
# 全部下载的列表网址， 也可以类似 https://www.esjzone.cc/tags/R18/ 包含 /tags/?/ 或 /list-??/
bookListURL = "https://www.esjzone.one/list-01/"
# 单次下载书籍URL
bookURL = "https://www.esjzone.one/detail/1624182605.html"
# 多线程数(esjzone被cloudflare反向代理的。可能有反爬虫机制，不建议调太大)
threadNum = 4
# 站点url 可能为 https://www.esjzone.cc/ 或 https://www.esjzone.me/
# 请确保bookListURL、bookURL、base_url的域名一致，同时esj.txt里cookie为对应的cookie！！！
base_url = "https://www.esjzone.one/"
# 代理
proxies = {
    'http': 'http://clash.dnsftp.com:7890',
    'https': 'http://clash.dnsftp.com:7890'
}


# esjzone 的 cookie请在浏览器中获取，将包含ews_key ews_token的cookie字符串(一行)填在脚本同文件夹下的esj.txt文件第一行

class ImgThreadSafeDict(object):
    def __init__(self):
        # 理论上用读写锁更好，但是需要第三方库
        self.lock = threading.Lock()
        self.imgByteDict = {}
        self.imgContentTypeDict = {}
        self.imgFilePathDict = {}
        self.imgOriginalUrlDict = {}

    def set(self, imgUrl):
        with self.lock:
            imgByte, imgType, imgHash, imgContentType = getImgData(imgUrl)
            if imgType is None:
                return f"<p>下载失败：{html.escape(urlHandler(imgUrl))}</p>"
            imgFileName = f"Image_{imgHash}{imgType}"
            if imgFileName not in self.imgFilePathDict:
                self.imgByteDict[imgFileName] = imgByte
                self.imgContentTypeDict[imgFileName] = imgContentType
                self.imgFilePathDict[imgFileName] = f"{imgFileName}"
                self.imgOriginalUrlDict[imgFileName] = imgUrl
            return f"<img src='{imgFileName}'/><br>"


class novelCharacterListNode(object):
    def __init__(self):
        self.isVolume = False
        self.isChapter = False
        self.level = 0
        self.value = 0
        self.title = ""
        self.url = ""
        self.fatherValue = -1
        # download处理
        self.content = ""
        self.txtValue = ""
        self.epubValue = epub.EpubHtml(lang="zh")
        self.lock = threading.Lock()
        self.isDone = False
        self.isLogged = False
        self.threadNum = 0
        self.childVolumeList = []

    def downloadCharacter(self, imgDict: ImgThreadSafeDict, threadNumValue: int = 0):
        if self.lock.locked():
            return
        with self.lock:
            if self.isDone:
                return
            self.threadNum = threadNumValue
            if self.isChapter:
                characterSoup = getSoupData(urlHandler(self.url))
                characterSoupDiv = characterSoup.find("div", {"class": "forum-content mt-3"})
                if characterSoupDiv is None or self.url is None or len(self.url) == 0:
                    self.txtValue = self.title + "章节下载失败" + "\n" + urlHandler(self.url) + "\n"
                    self.epubValue.title = self.title
                    self.epubValue.content = \
                        f"<html><head></head><body><h1>{html.escape(self.title)}</h1>" \
                        f"<p>章节下载失败</p><p>{html.escape(urlHandler(self.url))}</p></body></html>"
                    self.epubValue.file_name = f"error_novel_{self.value}.html"
                    self.epubValue.uid = "error_novel" + str(self.value)
                    return
                if characterSoupDiv.find("button", {"class": "btn btn-primary btn-send-pw"}) is not None:
                    self.content = "<p>本章节需要密码，已跳过</p>"
                else:
                    self.content = htmlSimplified(characterSoup, characterSoupDiv.contents, imgDict)
                if len(re.sub('\\s', '', self.content)) == 0:
                    self.content = "<p>【空】</p>"
                self.txtValue = self.title + "\n" + imgTagConvert(self.content, imgDict)
                self.epubValue.set_content(self.content)
                self.epubValue.title = self.title
                self.epubValue.file_name = f"novel_{self.value}.html"
                self.epubValue.uid = "novel" + str(self.value)
            else:
                self.txtValue = self.title + "\n"
                self.epubValue.title = self.title
                self.epubValue.file_name = f"volume_{self.value}.html"
                self.epubValue.content = f"<html><head></head><body><h1>{self.title}</h1></body></html>"
                self.epubValue.uid = "volume" + str(self.value)
        self.isDone = True


isTerminal = True


def printProgressBar(iteration, total, prefix='', suffix='', decimals=1, length=20, fill='█', printEnd="\r"):
    global isTerminal
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    if total == 0:
        return
    if not isTerminal:
        print(f"==={prefix} {int(iteration * 100 / total)}% {suffix}")
        return
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    try:
        t = os.get_terminal_size().columns
    except OSError:
        t = 0
        isTerminal = False
        print(f"==={prefix} {int(iteration * 100 / total)}% {suffix}")
    print("\r" + ' ' * t, end="\r")
    if t >= 36:
        m = t - 36
    else:
        m = 0
    print(f'\r{prefix} |{bar}| {percent}% {suffix[0:m]}', end=printEnd)
    if iteration == total:
        print()


class ThreadDownload(threading.Thread):
    def __init__(self, inputThreadNum, novelCharacterList: list, imgDict: ImgThreadSafeDict):
        threading.Thread.__init__(self)
        self.novelCharacterList = novelCharacterList
        self.imgDict = imgDict
        self.inputThreadNum = inputThreadNum

    def run(self):
        for character in self.novelCharacterList:
            assert isinstance(character, novelCharacterListNode)
            character.downloadCharacter(self.imgDict)
            if not character.isLogged:
                character.isLogged = True
                printProgressBar(character.value, len(self.novelCharacterList), prefix='进度:',
                                 suffix=character.title, length=20)


def getSoupData(url):
    r = DefaultResponse()
    soup = BeautifulSoup("", 'html.parser')
    try:
        r = retryGet(urlHandler(url), headers, (10, 25))
        r.raise_for_status()
        soup = BeautifulSoup(r.content, 'html.parser')
    except HTTPError as e:
        print("*x*x*x*http错误" + str(e))
    except Exception as e:
        print("*x*x*x*网络问题，请检测VPN等环境(最好使用TUN模式)" + str(e))
    finally:
        r.close()
        return soup
    # if r.encoding != "utf-8":
    #     text=r.text.encode(r.encoding).decode("utf-8")
    #     soup = BeautifulSoup(text, 'html5lib')
    #     r.close()
    #     return soup
    # else:
    #     soup = BeautifulSoup(r.content, 'html.parser')
    #     r.close()
    #     return soup


class DefaultResponse:
    def __init__(self):
        self.status_code = None

    def close(self):
        return


@retrying.retry(stop_max_attempt_number=3, wait_fixed=10 * 1000)
def retryGet(u, h, t):
    return requests.get(u, headers=h, timeout=t, proxies=proxies)


def getImgData(url):
    if url is None or len(url) == 0:
        return None, None, None, None
    extension_mapping = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'image/bmp': '.bmp',
        'image/tiff': '.tif',
        'image/webp': '.webp'
    }
    r = DefaultResponse()
    try:
        r = retryGet(urlHandler(url), headers_img, (25, 30))
        r.raise_for_status()
    except HTTPError as e:
        print("*x*x*x*http错误,img下载失败,url=" + url + "\n" + str(e))
    except Exception as e:
        print("*x*x*x*网络问题，请检测VPN等环境,url=" + url + "\n" + str(e))
    finally:
        if r.status_code == 200:
            # 返回值 图片比特值 图片后缀 图片hash值 图片Content-Type
            bytes_io = BytesIO(r.content)
            fileName = extension_mapping.get(r.headers.get('Content-Type'), None)
            resultHash = calculate_sha256_hash(BytesIO(r.content))
            contentType = r.headers.get('Content-Type')
            r.close()
            return bytes_io, fileName, resultHash, contentType
        else:
            return None, None, None, None


def calculate_sha256_hash(bytes_io_object):
    bytes_io_object.seek(0)
    sha256_hash = hashlib.sha256()
    sha256_hash.update(bytes_io_object.read())
    return sha256_hash.hexdigest()[:32]


def htmlSimplified(soup: BeautifulSoup, inputChildren: list[bs4.element.PageElement], imgDict: ImgThreadSafeDict):
    htmlResult = ""
    for child in inputChildren:
        if isinstance(child, Tag):
            if child.name == "img":
                htmlResult += imgDict.set(child['src'])
                continue
            if child.find("img") is not None:
                htmlResult += htmlSimplified(soup, child.contents, imgDict)
            else:
                for a in child.find_all("a"):
                    if a.get("isInsertedHrefValue") is not None:
                        continue
                    new_p_tag = soup.new_tag('p')
                    href = a.get('href')
                    if href is None or len(href) == 0:
                        continue
                    new_p_tag.string = f"[{href}]"
                    a.insert(0, new_p_tag)
                    a["isInsertedHrefValue"] = True
                if len(re.sub('\\s', '', child.get_text())) == 0:
                    continue
                text_content = child.get_text(separator='\n', strip=True)
                filtered_text = '\n'.join(line for line in text_content.split('\n') if line.strip())
                filtered_text = converter.convert(filtered_text)
                unescaped_string = html.escape(filtered_text)
                paragraphs = unescaped_string.splitlines()
                wrapped_paragraphs = ['<p>' + paragraph.strip() + '</p>' for paragraph in paragraphs]
                htmlResult += '\n'.join(wrapped_paragraphs)

        else:
            htmlResult += str(child)
    return htmlResult + '\n'


# def htmlSimplified(inputHtml, imgDict: ImgThreadSafeDict):
#     soup = BeautifulSoup(inputHtml, 'html.parser')
#     if soup.find("img") is not None:
#         htmlResult = ""
#         for child in soup.children:
#             if isinstance(child, Tag):
#                 childSoup = BeautifulSoup(str(child), 'html.parser')
#
#                 childContentsSoup = BeautifulSoup(features='html.parser')
#
#                 # childContents = str(''.join(map(str, childSoup.find(child.name).contents)))
#                 # childSoup = BeautifulSoup(str(child), 'html.parser')
#                 # if child.name == "img":
#                 #     htmlResult += imgDict.set(childSoup.find("img").get("src"))
#                 #     continue
#                 # if len(re.sub('\\s', '', childSoup.get_text())) != 0:
#                 #     htmlResult += htmlSimplified(childContents, imgDict)
#                 # else:
#                 #     inputStrChild = childSoup.find("img")
#                 #     inputStrChild = inputStrChild if inputStrChild is not None else ''
#                 #     htmlResult += htmlSimplified(str(inputStrChild), imgDict)
#             else:
#                 htmlResult += htmlSimplified(str(child), imgDict)
#         return htmlResult
#     else:
#         for a in soup.find_all("a"):
#             if a.get("isInsertedHrefValue") is not None:
#                 continue
#             new_p_tag = soup.new_tag('p')
#             href = a.get('href')
#             if href is None or len(href) == 0:
#                 continue
#             new_p_tag.string = f"[{href}]"
#             a.insert_before(new_p_tag)
#             a["isInsertedHrefValue"] = True
#         if len(re.sub('\\s', '', soup.get_text())) == 0:
#             return ""
#         text_content = soup.get_text(separator='\n', strip=True)
#         filtered_text = '\n'.join(line for line in text_content.split('\n') if line.strip())
#         filtered_text = converter.convert(filtered_text)
#         unescaped_string = html.escape(filtered_text)
#         paragraphs = unescaped_string.splitlines()
#         wrapped_paragraphs = ['<p>' + paragraph.strip() + '</p>' for paragraph in paragraphs]
#         result = '\n'.join(wrapped_paragraphs)
#         return result + '\n'


def contentsAnalysis(inputChildren: list[bs4.element.PageElement], novelCharacterList: list,
                     levelValue: int, fatherValue: int):
    depth = 0
    depth = max(depth, levelValue)
    childContentsCount = 0
    while childContentsCount < len(inputChildren):
        child = inputChildren[childContentsCount]
        if isinstance(child, Tag):
            if child.name == 'p' and len(re.sub('\\s', '', child.get_text())) == 0:
                childContentsCount += 1
                continue
            node = novelCharacterListNode()
            node.level = levelValue
            node.value = len(novelCharacterList)
            node.fatherValue = fatherValue
            novelCharacterList.append(node)
            if child.name == "details":
                summary = child.find("summary")
                node.title = converter.convert(summary.get_text()) if summary else ""
                if node.title is None or len(re.sub('\\s', '', node.title)) == 0:
                    node.title = "卷"
                startNum = 1
                if summary is None:
                    startNum = 0
                depth = max(depth,
                            contentsAnalysis(child.contents[startNum:], novelCharacterList, levelValue + 1, node.value))
                node.isVolume = True
            elif child.name == "p" and len(re.sub('\\s', '', child.get_text())) != 0:
                node.title = converter.convert(child.get_text())
                nextP = childContentsCount + 1
                while nextP < len(inputChildren):
                    nextChild = inputChildren[nextP]
                    if isinstance(nextChild, Tag):
                        if nextChild.name == "p" and len(re.sub('\\s', '', nextChild.get_text())) != 0:
                            break
                    nextP += 1
                depth = max(depth, contentsAnalysis(inputChildren[childContentsCount + 1:nextP], novelCharacterList,
                                                    levelValue + 1, node.value))
                childContentsCount = nextP
                node.isVolume = True
                continue
            elif child.name == "a":
                node.title = converter.convert(child.get_text())
                node.url = child.get("href")
                node.isChapter = True

        childContentsCount += 1
    return depth


# def contentsAnalysis(inputChildren: list[bs4.element.PageElement],
#                      novelCharacterList: list, levelValue: int, fatherValue: int):
#     depth = 0
#     depth = max(depth, levelValue)
#     removeList = []
#     for child in inputChildren:
#         if not isinstance(child, Tag):
#             if len(re.sub('\\s', '', str(child))) == 0:
#                 removeList.append(child)
#         else:
#             if len(re.sub('\\s', '', child.get_text())) == 0:
#                 removeList.append(child)  # 这里不能直接remove，会导致迭代器跳过部分元素
#     for child in removeList:
#         child.extract()
#     for childContentsCount in range(len(inputChildren)):
#         if childContentsCount >= len(inputChildren):
#             break  # 防止迭代器越界
#         child = inputChildren[childContentsCount]
#         if isinstance(child, Tag):
#             if child.name == "details":
#                 depth = max(depth, contentsAnalysis(child.contents, novelCharacterList, levelValue, fatherValue))
#                 continue
#             node = novelCharacterListNode()
#             node.level = levelValue
#             node.value = len(novelCharacterList)
#             node.fatherValue = fatherValue
#             novelCharacterList.append(node)
#             node.title = converter.convert(child.get_text())
#             if child.name == "p" or child.name == "summary":
#                 subSoupList = []
#                 while childContentsCount + 1 < len(inputChildren):
#                     nextChild = inputChildren[childContentsCount + 1]
#                     if isinstance(nextChild, Tag):
#                         if nextChild.name == "a":
#                             subSoupList.append(nextChild.extract())
#                         elif nextChild.name == "details":
#                             subSoupList.append(nextChild.extract())
#                         else:
#                             break
#                 depth = max(depth, contentsAnalysis(subSoupList, novelCharacterList, levelValue + 1, node.value))
#                 node.isVolume = True
#             elif child.name == "a":
#                 node.url = child['href']
#                 node.isChapter = True
#     return depth

def imgTagConvert(inputHtml, imgDict: ImgThreadSafeDict):
    soup = BeautifulSoup(inputHtml, 'html.parser')
    for img_tag in soup.find_all("img"):
        new_p_tag = soup.new_tag('p')
        new_p_tag.string = imgDict.imgOriginalUrlDict[img_tag['src']]
        img_tag.replace_with(new_p_tag)
    return soup.get_text(separator='\n', strip=True) + "\n"


# 他妈的防御性编程，反反复复爬了一堆然后就报错，一看，哦，页面不规范，缺这个缺那的
def downloadOneBook(url):
    epubCreateBook = epub.EpubBook()
    epubCreateBook.set_identifier(str(uuid.uuid4()))
    epubCreateBook.set_language("zh")
    txtCreateBook = ""
    epubImgDict = ImgThreadSafeDict()

    # 书籍基本信息获取
    soupContent = getSoupData(url)
    if soupContent.find("h2") is None:
        print("*x*x*x*cookie无效,未登录。也有可能esjzone.cc和esjzone.me的cookie不通用[遇到重定向]")
        return None, None, None
    bookName = converter.convert(soupContent.find("h2").text)
    bookAuthorTag = soupContent.find("ul", {"class": "list-unstyled mb-2 book-detail"})
    bookAuthor = converter.convert(bookAuthorTag.find("a").text) if bookAuthorTag and bookAuthorTag.find("a") else ""
    # 替换文件名中不允许的字符
    bookName = re.sub(r'[\\/:*?"<>|]', '', bookName)
    bookAuthor = re.sub(r'[\\/:*?"<>|]', '', bookAuthor)
    # 他妈的日本傻逼轻小说名过长会引起File name too long错误！
    if len(bookName) > 48:
        bookName = bookName[:47] + '…'
    if len(bookAuthor) > 16:
        bookAuthor = bookAuthor[:15] + '…'
    epubCreateBook.set_title(bookName)
    epubCreateBook.add_author(bookAuthor)
    bookChangeDate = ""
    if bookAuthorTag:
        bookAuthorText = bookAuthorTag.get_text()
        dates = re.findall(r'\d{4}-\d{2}-\d{2}', bookAuthorText)
        if dates:
            bookChangeDate = dates[-1]
    epubCreateBook.add_metadata(None, 'meta', '', {'name': 'esjLastChangeDate', 'content': bookChangeDate})
    if isDownloadAll and path.exists(f"./epubBooks_esjzone/《{bookName}》{bookAuthor}.epub"):
        existBook = epub.read_epub(f"./epubBooks_esjzone/《{bookName}》{bookAuthor}.epub", {'ignore_ncx': True})
        existBookLastChangeDate = ''
        try:
            existBookLastChangeDate = existBook.get_metadata('OPF', 'esjLastChangeDate')[0][1]['content']
        except Exception as e:
            pass
        if existBookLastChangeDate == bookChangeDate and existBookLastChangeDate != '' and bookChangeDate != '':
            print(f"《{bookName}》{bookAuthor} 更新日期{bookChangeDate} 已存在")
            return bookName, bookAuthor, bookChangeDate
    print("-" + bookName + "开始下载\n")
    # 封面尝试获取
    if soupContent.find("div", {"class": "product-gallery text-center mb-3"}) is not None:
        coverUrl = urlHandler(
            soupContent.find("div", {"class": "product-gallery text-center mb-3"}).find("img").get("src"))
        coverData, coverDataTypeName, _, coverDataType = getImgData(coverUrl)
        if coverDataTypeName is not None:
            epubCreateBook.set_cover("cover" + coverDataTypeName, coverData.getvalue())
            coverHtml = epub.EpubHtml(uid="coverHtml", title="封面", file_name="cover.html", lang="zh")
            coverHtml.content = f"<img src='cover{coverDataTypeName}'/>"
            epubCreateBook.add_item(coverHtml)
            epubCreateBook.toc.append(coverHtml)
            epubCreateBook.spine.append(coverHtml)
    # 简介获取
    bookDescription = epub.EpubHtml(uid="description", title="简介", file_name="description.html", lang="zh")
    if soupContent.find("div", {"class": "description"}) is not None:
        bookDescription.content = htmlSimplified(soupContent,
                                                 soupContent.find("div", {"class": "description"}).contents,
                                                 epubImgDict)
        if len(re.sub('\\s', '', bookDescription.content)) == 0:
            bookDescription.content = "<p>【空】</p>"
        epubCreateBook.add_item(bookDescription)
        epubCreateBook.toc.append(bookDescription)
        epubCreateBook.spine.append(bookDescription)
        txtCreateBook += "简介\n" + imgTagConvert(bookDescription.content, epubImgDict)
    # 章节获取

    novelCharacterList = []
    chapterList = soupContent.find("div", {"id": "chapterList"})
    if chapterList is None:
        return None, None, None
    depth = contentsAnalysis(chapterList.contents, novelCharacterList, 0, -1)
    # 多线程下载
    threadList = []
    for threadCount in range(0, threadNum):
        threadList.append(ThreadDownload(threadCount, novelCharacterList, epubImgDict))
        sleep(0.1)
    for thread in threadList:
        thread.start()
    for thread in threadList:
        thread.join()
    printProgressBar(len(novelCharacterList), len(novelCharacterList), prefix='进度:', suffix="下载完成", length=20)
    # 书籍保存
    print()
    print(f"={bookName}章节下载完成")
    for character in novelCharacterList:
        epubCreateBook.add_item(character.epubValue)
        epubCreateBook.spine.append(character.epubValue)
        txtCreateBook += character.txtValue
    epubCreateBook.toc.extend(listAnalysisToc(novelCharacterList, depth))
    for pic in epubImgDict.imgFilePathDict:
        epubCreateBook.add_item(
            epub.EpubImage(uid=str(pic), file_name=epubImgDict.imgFilePathDict[pic],
                           media_type=epubImgDict.imgContentTypeDict[pic],
                           content=epubImgDict.imgByteDict[pic].getvalue()))
    epubCreateBook.add_item(epub.EpubNcx())
    epubCreateBook.add_item(epub.EpubNav())

    if not path.exists("./epubBooks_esjzone"):
        mkdir("./epubBooks_esjzone")
    if not path.exists("./txtBooks_esjzone"):
        mkdir("./txtBooks_esjzone")
    
    epub.write_epub(f"./epubBooks_esjzone/《{bookName}》{bookAuthor}.epub", epubCreateBook, {})
    with open(f"./txtBooks_esjzone/《{bookName}》{bookAuthor}.txt", "w", encoding="utf-8") as txtFile:
        txtFile.write(txtCreateBook)
    print(f"《{bookName}》{bookAuthor} 日期{bookChangeDate}下载完成")
    return bookName, bookAuthor, bookChangeDate


def listAnalysisToc(inputList: list[novelCharacterListNode], maxDepth: int):
    resultList = []
    for inputNode in inputList:
        if inputNode.epubValue.content is None or len(inputNode.epubValue.content) == 0:
            print()
        if len(re.sub('\\s', '', BeautifulSoup(inputNode.epubValue.content, 'html.parser').get_text())) == 0:
            print()
    for depth in range(maxDepth, -1, -1):
        for character in inputList:
            if character.level == depth:
                if character.isVolume:
                    volumeTuple = (epub.Section(character.title, character.epubValue.file_name),
                                   character.childVolumeList)
                    if character.fatherValue == -1:
                        resultList.append(volumeTuple)
                    else:
                        inputList[character.fatherValue].childVolumeList.append(volumeTuple)
                if character.isChapter:
                    if character.fatherValue == -1:
                        resultList.append(character.epubValue)
                    else:
                        inputList[character.fatherValue].childVolumeList.append(character.epubValue)

    return resultList


# firefoxSeDriverOptions = Options()
# if not debug:
#     firefoxSeDriverOptions.add_argument("--headless")
# firefoxSeDriverOptions.binary_location = r"G:\\Firefox\\App\\Firefox64\\firefox.exe"
# firefoxSeDriverOptions.add_argument("-profile")
# firefoxSeDriverOptions.add_argument('G:\\Firefox\\Data\\profile')
# firefoxSeDriver = webdriver.Firefox(options=firefoxSeDriverOptions)
#
# firefoxSeDriver.get(bookListURL)
#
#
# cookies = firefoxSeDriver.get_cookies()
# for cookie in cookies:
#     print(cookie)
# # 获取小说名
# firefoxSeDriver.quit()
def urlHandler(url):
    if url is None:
        return ""
    if not urlparse(url).scheme:
        return urljoin(base_url, url)
    else:
        return url


headers_img = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
               "Accept": "image/avif,image/webp,*/*",
               "Connection": "keep-alive",
               "Sec-Fetch-Dest": "image",
               "Sec-Fetch-Mode": "no-cors",
               "Sec-Fetch-Site": "cross-site",
               "Pragma": "no-cache",
               "Cache-Control": "no-cache",
               "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2"}
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
           "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
           "Connection": "keep-alive", "Upgrade-Insecure-Requests": "1",
           "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "cross-site",
           "Pragma": "no-cache", "Cache-Control": "no-cache"}
read_me = """# ESJZone 的简中小说EPUB全部备份

从项目 [/ZALin/ESJZone-novel-mirror/](https://github.com/ZALin/ESJZone-novel-mirror/tree/main) 修改而来

包含原项目已经备份小说

### 备份说明
1. EPUB格式包含图片(尽可能尝试下载)，超链接文本。并且尝试分析目录。不备份文字css样式。文本格式包含图片源地址。超链接文本
2. 原项目小说备份位于Novel文件夹下。本项目备份epub小说位于/epubBooks_esjzone。新txt备份位于/txtBooks_esjzone
3. 不备份备份时间已经已经下架小说，密码页面跳过

### 手动更新使用方法
1. 确保你拥有基本的python知识和命令行使用方法
2. 命令行执行 `pip install beautifulsoup4 ebooklib opencc requests retrying`
3. 打开py文件。更改位于开头参数
- 繁简转换。
  - 默认为繁体转简体。如需要简体转繁体将`converter = opencc.OpenCC('t2s.json')`里的`t2s.json`改为`s2t.json`
- 小说下载
  - 若需要下载单本小说。使`isDownloadAll = False`。然后更改`bookURL`变量值。网址包含detail，类似于`https://www.esjzone.cc/detail/1557379934.html`
  - 若需要备份全部小说或某一类别全部小说。使`isDownloadAll = True`。然后更改`bookListURL`变量值。应包含tag或list。类似于`https://www.esjzone.cc/list-04/`或 `https://www.esjzone.cc/tags/R18/`
- Cookie设置
  - 部分书籍需要设置cookie打开浏览器，登录esjzone。自行搜索浏览器cookie复制方法。复制`ews_key` `ews_key`两个cookie变量，填入`esj.py`脚本所在文件夹下的`esj.txt`中。使其看起来类似于
    ```
    ews_key=AAAAAAAAAAAAAAAA;ews_token=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB;
    ```
- 线程下载数
 - 默认为2。想要下载快一些可以调大。不建议调太大防止引发站点反爬虫机制
- 站点url
    - 可能为 `https://www.esjzone.cc/` 或 `https://www.esjzone.me/`。请确保bookListURL、bookURL、base_url的域名一致
4. 命令行执行`python esj.py`。等待下载完成

### 项目fork时间
2024/02/03
### 项目更新时间
"""
if __name__ == "__main__":
    warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
    with open("./esj.txt", "r", encoding="utf-8") as cookieFile:
        cookie = cookieFile.readline().strip()
        headers["Cookie"] = cookie
    parseBaseURL = urlparse(base_url)
    if isDownloadAll:
        paseBookListURL = urlparse(bookListURL)
        if parseBaseURL.netloc != paseBookListURL.netloc or parseBaseURL.scheme != paseBookListURL.scheme:
            print("请确保bookListURL、base_url的协议与域名一致")
            sys.exit(1)
    else:
        paseBookURL = urlparse(bookURL)
        if parseBaseURL.netloc != paseBookURL.netloc or parseBaseURL.scheme != paseBookURL.scheme:
            print("请确保bookURL、base_url的协议与域名一致")
            sys.exit(1)
    response = requests.get(base_url, headers=headers, timeout=(10, 25), allow_redirects=False, proxies=proxies)
    if response.status_code == 301 or response.status_code == 302:
        print("请修改base_url为重定向后的url: " + response.headers['Location'])
        print("请确保bookListURL或bookURL与base_url的域名一致")
        print("请确保cookie是否为该base_url的cookie")
        sys.exit(2)
    if isDownloadAll:
        read_me += "\n" + datetime.now().strftime("%Y/%m/%d") + "\n### 本项目更新书籍列表\n"
        bookUrlList = []
        listSoup = getSoupData(bookListURL)
        print(converter.convert(listSoup.find("h1").text) + "下载中")
        bookListNum = 0
        scripts = listSoup.find_all('script')
        for script in scripts:
            if str(script).find('total') != -1:
                match = re.search(r'total: (\d+)', str(script))
                if match:
                    bookListNum = int(match.group(1))
                    break
        print("小说列表下载")
        for i in range(1, bookListNum + 1):
            bookListPageURL = bookListURL + f"{i}.html"
            listSoup = getSoupData(bookListPageURL)
            bookList = listSoup.find_all("div", {"class": "col-lg-3 col-md-4 col-sm-3 col-xs-6"})
            for b in bookList:
                bookUrlList.append(urlHandler(b.find("a").get("href")))
            printProgressBar(i, bookListNum, prefix='进度:', length=20)
        print("共" + str(len(bookUrlList)) + "本小说")
        for index, bookURL in enumerate(bookUrlList):
            name, author, bookDate = downloadOneBook(bookURL)
            if name is None:
                continue
            read_me += f"- 《{name}》{author} 更新日期{bookDate}\n"
            print("已下载" + str(bookUrlList.index(bookURL) + 1) + "本小说,进度"
                  + str(int((bookUrlList.index(bookURL) + 1) * 100 / len(bookUrlList))) + "%")
            if index % 100 == 0 and index != 0:
                process = psutil.Process(os.getpid())
                mem = process.memory_info()[0] / float(2 ** 20)
                print(f"··当前内存使用{mem:.2f}MB")
                gc.collect()
                process = psutil.Process(os.getpid())
                mem = process.memory_info()[0] / float(2 ** 20)
                print(f"··回收后当前内存使用{mem:.2f}MB")
        with open("./README.md", "w", encoding="utf-8") as readmeFile:
            readmeFile.write(read_me)
    else:
        downloadOneBook(bookURL)
