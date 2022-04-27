from ezodf import newdoc
import os
import zipfile
import tempfile
namef = 'certificado.odt'
odt = newdoc(doctype='odt', filename=namef, template='certificado.odt')
odt.save()
a = zipfile.ZipFile('certificado.odt')
content = a.read('content.xml')
content = str(content.decode(encoding='utf8'))
content = str.replace(content,"PERAZZO", '123')
content = str.replace(content, 'RAFAEL', '456')



def updateZip(zipname, filename, data):
    # generate a temp file
    tmpfd, tmpname = tempfile.mkstemp(dir=os.path.dirname(zipname))
    os.close(tmpfd)

    # create a temp copy of the archive without filename
    with zipfile.ZipFile(zipname, 'r') as zin:
        with zipfile.ZipFile(tmpname, 'w') as zout:
            zout.comment = zin.comment # preserve the comment
            for item in zin.infolist():
                if item.filename != filename:
                    zout.writestr(item, zin.read(item.filename))

    # replace with the temp archive
    os.remove(zipname)
    os.rename(tmpname, zipname)

    # now add filename with its new data
    with zipfile.ZipFile(zipname, mode='a', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, data)

updateZip(namef, 'content.xml', content)
