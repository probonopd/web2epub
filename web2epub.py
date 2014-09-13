#!python
# -*- coding: utf-8 -*-

# web2epub is a command line tool to convert a set of web/html pages to epub.
# Copyright 2012 Rupesh Kumar
# Copyright 2014 Simon Peter

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA.

import zipfile, urllib, sys, os.path, mimetypes, time, urlparse
from optparse import OptionParser
#from readability.readability import Document
import readability
import cssselect # readability needs it; importing here so that we see if it is not present
from BeautifulSoup import BeautifulSoup,Tag

from xml.sax.saxutils import escape

class MyZipFile(zipfile.ZipFile):
    def writestr(self, name, s, compress=zipfile.ZIP_DEFLATED):
        zipinfo = zipfile.ZipInfo(name, time.localtime(time.time())[:6])
        zipinfo.compress_type = compress
        zipfile.ZipFile.writestr(self, zipinfo, s)

def ascii_chars(string):
    """Returns ASCII characters only and skipps all others.
    """
    return ''.join(char for char in string if ord(char) < 128)

def build_command_line():
    parser = OptionParser(usage="Usage: %prog [options] url1 url2 ...urln")
    parser.add_option("-t", "--title", dest="title", help="title of the epub")
    parser.add_option("-a", "--author", dest="author", help="author of the epub")
    parser.add_option("-c", "--cover", dest="cover", help="path to cover image")
    parser.add_option("-o", "--outfile", dest="outfile", help="name of output file")
    parser.add_option('-i','--images', help='Include images', action='store_true')
    parser.add_option('-f','--footer', help='Include footer with source URL', action='store_true')
    parser.add_option('-l','--links', help='Preserve links in the articles', action='store_true')
    parser.add_option('-L','--language', help='Language')
    return parser

def web2epub(urls, outfile=None, cover=None, title=None, author=None, images=None, footer=None, links=None, language=""):

    if(outfile == None):
        outfile = time.strftime('%Y-%m-%d-%S.epub')

    nos = len(urls)
    cpath = 'data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=='
    ctype = 'image/gif'
    if cover is not None:
        cpath = 'images/cover' + os.path.splitext(os.path.abspath(cover))[1]
        ctype = mimetypes.guess_type(os.path.basename(os.path.abspath(cover)))[0]

    epub = MyZipFile(outfile, 'w', zipfile.ZIP_DEFLATED)

    # The first file must be named "mimetype"
    epub.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
    # We need an index file, that lists all other HTML files
    # This index file itself is referenced in the META_INF/container.xml file
    epub.writestr("META-INF/container.xml", '''<container version="1.0"
        xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
        <rootfiles>
            <rootfile full-path="OEBPS/Content.opf" media-type="application/oebps-package+xml"/>
        </rootfiles>
        </container>''')

    # The index file is another XML file, living per convention
    # in OEBPS/content.opf
    index_tpl = '''<package version="2.0"
        xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid">
        <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>%(title)s</dc:title>
        <dc:creator>%(author)s</dc:creator>
        <dc:date>%(date)s</dc:date>
        <dc:language>%(lang)s</dc:language>
        <meta name="cover" content="cover-image" />
        </metadata>
        <manifest>
          <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
          <item id="cover" href="cover.html" media-type="application/xhtml+xml"/>
          <item id="cover-image" href="%(front_cover)s" media-type="%(front_cover_type)s"/>
          <item id="css" href="stylesheet.css" media-type="text/css"/>
            %(manifest)s
        </manifest>
        <spine toc="ncx">
            <itemref idref="cover" linear="no"/>
            %(spine)s
        </spine>
        <guide>
            <reference href="cover.html" type="cover" title="Cover"/>
        </guide>
        </package>'''

    toc_tpl = '''<?xml version='1.0' encoding='utf-8'?>
        <!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN"
                 "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
        <ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
        <head>
        <meta name="dtb:depth" content="1"/>
        <meta name="dtb:totalPageCount" content="0"/>
        <meta name="dtb:maxPageNumber" content="0"/>
      </head>
      <docTitle>
        <text>%(title)s</text>
      </docTitle>
      <navMap>
        <navPoint id="navpoint-1" playOrder="1"> <navLabel> <text>Cover</text> </navLabel> <content src="cover.html"/> </navPoint>
        %(toc)s
      </navMap>
    </ncx>'''

    cover_tpl = '''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head>
        <title>Cover</title>
        <style type="text/css"> img { max-width: 100%%; } </style>
        </head>
        <body>
        <div class="centerpage">
        <h1>%(title)s</h1>
        <div id="cover-image">
        <img src="%(front_cover)s" alt="Cover image"/>
        </div>
        </div>
        </body>
        </html>'''

    stylesheet_tpl = '''
        p, body {
            orphans: 2;
            widows: 2;
        }

        .centerpage{
            text-align:center; /* center horizontally */
            vertical-align:middle; /* center vertically */
        }
    '''

    manifest = ""
    spine = ""
    toc = ""

    for i,url in enumerate(urls):
        print "Reading URL %s of %s --> %s " % (i+1,nos,url)
        ##try:
        req = urllib.urlopen(url)
        # http://stackoverflow.com/questions/1020892/urllib2-read-to-unicode
        encoding=req.headers['content-type'].split('charset=')[-1]
        html = req.read()
        html = unicode(html, encoding)
        ##except:
            ##continue
        readable_article = None
        ##try:
        document = readability.Document(html)
        document.TEXT_LENGTH_THRESHOLD = 200 # Gives better results than default
        readable_article = document.summary()
        readable_title = document.short_title()
        ##except:
            ##continue
        
        if(readable_article == None):
            continue

        manifest += '<item id="article_%s" href="article_%s.html" media-type="application/xhtml+xml"/>\n' % (i+1,i+1)
        spine += '<itemref idref="article_%s" />\n' % (i+1)
        toc += '<navPoint id="navpoint-%s" playOrder="%s"> <navLabel> <text>%s</text> </navLabel> <content src="article_%s.html"/> </navPoint>' % (i+2,i+2,repr(readable_title),i+1)

        try:
            soup = BeautifulSoup(readable_article)
            #Add xml namespace
            soup.html["xmlns"] = "http://www.w3.org/1999/xhtml"
        except:
            continue

        # Insert header if it is not already there
        body = soup.html.body
        if not(ascii_chars(readable_title) in ascii_chars(readable_article)): # TODO: FIXME, this does not work yet, e.g., for ZEIT
            h1 = Tag(soup, "h1", [("class", "title")])
            h1.insert(0, escape(readable_title))
            body.insert(0, h1)

        if(links == None):
            refs = body.findAll('a')
            for x in refs:
                try:
                    tag = Tag(soup,'span', [("class", "link-removed")])
                    tag.insert(0,x.text)
                    body.a.replaceWith(tag)
                except:
                    pass

        #Add stylesheet path
        head = soup.find('head')
        if head is None:
            head = Tag(soup,"head")
            soup.html.insert(0, head)
        link = Tag(soup, "link", [("type","text/css"),("rel","stylesheet"),("href","stylesheet.css")])
        head.insert(0, link)
        article_title = Tag(soup, "title")
        article_title.insert(0, escape(readable_title))
        head.insert(1, article_title)

        # If we do not have an author for the book, then use the URL hostname of the first article
        if(author == None):
            author = str(urlparse.urlparse(url).hostname.replace("www.","")) or ''

        # If we do not have a title for the book, then use the date
        if(title == None):
            if(len(urls)>1):
                title = author + " " + str(time.strftime('%d.%m.%Y'))
                # title = readable_title
            else:
                title = readable_title

        if(images != None):
            #Download images
            for j,image in enumerate(soup.findAll("img")):
                #Convert relative urls to absolute urls
                imgfullpath = urlparse.urljoin(url, image["src"])
                #Remove query strings from url
                imgpath = urlparse.urlunsplit(urlparse.urlsplit(imgfullpath)[:3]+('','',))
                print "    Downloading image: %s %s" % (j+1, imgpath)
                imgfile = os.path.basename(imgpath)
                os.system("mogrify -resize 1200x1200 -quality 50 " + imgpath)
                filename = 'article_%s_image_%s%s' % (i+1,j+1,os.path.splitext(imgfile)[1])
                if imgpath.lower().startswith("http"):
                    epub.writestr('OEBPS/images/'+filename, urllib.urlopen(imgpath).read())
                    image['src'] = 'images/'+filename
                    manifest += '<item id="article_%s_image_%s" href="images/%s" media-type="%s"/>\n' % (i+1,j+1,filename,mimetypes.guess_type(filename)[0])

        if(footer != None):
            p =  Tag(soup, "p", [("class", "source-url")])
            p.insert(0, url)
            body.append(p)

        epub.writestr('OEBPS/article_%s.html' % (i+1), str(soup))

    #Metadata about the book
    info = dict(title=(title).encode('ascii', 'xmlcharrefreplace'),
            author=(author).encode('ascii', 'xmlcharrefreplace'),
            date=time.strftime('%Y-%m-%d'),
            lang=language,
            front_cover= cpath,
            front_cover_type = ctype
            )

    epub.writestr('OEBPS/cover.html', cover_tpl % info)
    if cover is not None:
        epub.write(os.path.abspath(cover),'OEBPS/images/cover'+os.path.splitext(cover)[1],zipfile.ZIP_DEFLATED)

    info['manifest'] = manifest
    info['spine'] = spine
    info['toc']= toc

    # Finally, write the index and toc
    epub.writestr('OEBPS/stylesheet.css', stylesheet_tpl)
    epub.writestr('OEBPS/Content.opf', index_tpl % info)
    epub.writestr('OEBPS/toc.ncx', toc_tpl % info)
    return outfile

if __name__ == '__main__':
    parser = build_command_line()
    (options, urls) = parser.parse_args()
    web2epub(urls, cover=options.cover, outfile=options.outfile, title=options.title, author=options.author, images=options.images, footer=options.footer, links=options.links)
