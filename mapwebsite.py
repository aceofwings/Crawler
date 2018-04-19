import argparse
import logging
import urllib.request
import collections
from urllib.parse import scheme_chars
import re
import queue
import threading
from bs4 import BeautifulSoup
import time

aP = argparse.ArgumentParser(description="Scrapes web links")

aP.add_argument('url', help="url of website being scraped")

aP.add_argument('--ofilem', metavar='o', help="output to file")

aP.add_argument('--limit' , metavar='l', help="limit search to given domain")

aP.add_argument('--threaded', metavar='t', help="number of threads (defaults to 4 threads)",type=int,default=4)

aP.add_argument('--mulch', metavar='m', help="output only the URLs of pages within the domain and not broken", action='store_const', const=True)

aP.add_argument('--verbose', metavar='p', help="print out stuff",action='store_const', const=True)


IP_RE = re.compile(r'^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$')


verbose = False
#list of known tld exceptions.
tldExceptions = ['co.uk','com','gov','net','org']
#remove the https to expose full domain
SCHEME_RE = re.compile(r'^([' + scheme_chars + ']+:)?//')

broken_pages = []

class ATag(object):
    broken = False
    def __init__(self,url):
        self.netloc = self.network_location(url)
        self.url = url
        self.build_url_attrs()

        if len(self.full_domain) == 0: #attempt resoultion
            self.full_domain = VisitCache.main_url.netloc
            self.url = 'http://' + self.full_domain + url
            self.netloc = self.network_location(self.url)
            self.build_url_attrs()

    def build_url_attrs(self):
        lower_labels = [label.lower() for label in self.netloc.split(".")]
        self.suffix_offset = find_tld(lower_labels)
        self.tld = ".".join(lower_labels[self.suffix_offset:])
        self.full_domain = ".".join(lower_labels[:self.suffix_offset])
        self.subdomain, s , self.domain = self.full_domain.rpartition(".")


    def network_location(self,url):
        return SCHEME_RE.sub("", url) \
        .partition("/")[0] \
        .partition("?")[0] \
        .partition("#")[0] \
        .split("@")[-1] \
        .partition(":")[0] \
        .strip() \
        .rstrip(".")


    def __hash__(self):
        return hash(self.url)

    def __eq__(self,other):
        return self.url == other.url

    def __repr__(self):
        return self.url +  " "

    def visit(self):
        """ return a list of urls for this page """
        VisitCache.visit_urls.add(self)
        if verbose:
            print("Visiting " + self.url)
        html_page = None
        try:
            html_page = urllib.request.urlopen(self.url,timeout=10)
        except urllib.error.HTTPError as msg:
            try:
                req = urllib.request.Request(self.url, headers={'User-Agent' : "Love Browser"})
                html_page = urllib.request.urlopen(req,timeout=10)
            except Exception as msg:
                self.broken = True
                print(msg)
                broken_pages.append(self)
                return []
        except Exception as msg:
            return []

        self.page_code = html_page.getcode()
        if self.page_code == 404:
            broken_pages.append(self)
            self.broken = True
        soup = None
        try:
            soup = BeautifulSoup(html_page, 'html.parser')
        except:
            return []
        return [ATag(a_tag['href']) for a_tag in soup.findAll('a', href=True)]



    def visit_dry(self):
        try:
            html_page = urllib.request.urlopen(self.url,timeout=2)
            self.page_code = html_page.getcode()
            if self.page_code == 404:
                self.broken = True
        except Exception :
            pass

        VisitCache.visit_urls.add(self)
        return []

    def mark_visit(self):
        VisitCache.visit_urls.add(self)




class VisitCache(object):
    main_url = None
    visit_urls = set()
    urls = set()
    interations = 0
    def not_visted(self,urls):
        pass

    def visited(self,urls):
        pass

    def broken(self,urls):
        pass
    @classmethod
    def print_found_urls(cls):
        shown = 0
        for url in cls.visit_urls:
            print(url.url + " : ", "Broken? : " + str(url.broken))
            shown += 1

        print("Total Urls Visited ", str(len(cls.visit_urls)), " Shown : q", str(shown))

    @classmethod
    def print_local_urls(cls):
        for url in cls.visit_urls:
            if url.domain == cls.main_url.domain:
                print(url.url + " : ", "Broken? : " + str(url.broken))

    @classmethod
    def print_local_not_broken(cls):
        for url in cls.visit_urls:
            if url.domain == cls.main_url.domain and not url.broken:
                print(url.url + " : ", "Broken? : " + str(url.broken))

    @classmethod
    def print_broken_urls(cls):
        print("=================BROKEN PAGES ============================")
        for url in broken_pages:
            print (url.url)

        print("Number broken " + str(len(broken_pages)) + " pages" )








class Crawler(object):

    def __init__(self,workers=4):
        self.i = 0
        self.q = queue.Queue()
        self.e = threading.Event()
        self.workers = workers
        for i in range(workers):
            t = threading.Thread(target=self.crawl_worker)
            t.daemon = True
            t.start()

    def quit_workers(self):
        for i in range(self.workers):
            with self.q.mutex:
                self.q.queue.clear()
            self.q.put(None)
    def crawl(self):
        self.urls = set()
        for url in VisitCache.urls:
            if VisitCache.main_url.domain == url.domain:
                self.urls.update(url.visit())
                self.i+= 1
            else:
                url.visit_dry()
                self.i += 1
        VisitCache.urls.update(self.urls)
        VisitCache.urls.difference_update(VisitCache.visit_urls)

        if len(VisitCache.urls) == 0:
            return
        self.crawl()

    def multi_crawl(self):
        self.urls = set()
        self.e = threading.Event()
        for url in VisitCache.urls:
            if VisitCache.main_url.domain == url.domain:
                self.q.put(url.visit)
            else:
                self.q.put(url.visit_dry)
        self.q.join()
        VisitCache.urls.update(self.urls)
        VisitCache.urls.difference_update(VisitCache.visit_urls)
        if len(VisitCache.urls) == 0:
            return
        self.multi_crawl()

    def crawl_worker(self):
        while True:
            task = self.q.get()
            if task is None:
                break
            self.urls.update(task())
            self.q.task_done()
            self.i += 1




def find_tld(lower_labels):
    for i in range(len(lower_labels)):
        possible_tld = ".".join(lower_labels[i:])
        if possible_tld in tldExceptions:
            return i

    return len(lower_labels)


if __name__ == '__main__':
    try:
        arguments = aP.parse_args()
        main_url_o = ATag(arguments.url)
        VisitCache.main_url = main_url_o
        VisitCache.urls.update([main_url_o])
        verbose = arguments.verbose
        c = None
        if arguments.threaded is not None:
            c = Crawler(workers=arguments.threaded)
            c.multi_crawl()
            c.quit_workers()
        else:
            c = Crawler()
            c.crawl()

        if arguments.mulch is not None:
            VisitCache.print_local_not_broken()
        else:
            VisitCache.print_found_urls()
    except SystemExit:
        c.quit_workers()
        VisitCache.print_found_urls()
        VisitCache.print_broken_urls()
    except KeyboardInterrupt:
        c.quit_workers()
        VisitCache.print_found_urls()
        VisitCache.print_broken_urls()
