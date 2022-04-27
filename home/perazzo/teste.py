import MySQLdb
host = "mysql://pesquisa:h5YACshdpuHfXx84@db/pesquisa"
conn = MySQLdb.connect(host="db", user="pesquisa", passwd="h5YACshdpuHfXx84", db="pesquisa", charset="utf8", 
use_unicode=True)
conn.select_db('pesquisa')
cursor  = conn.cursor()
consulta = """SELECT id,nome,DATE_FORMAT(deadline,'%d/%m/%Y - %H:%i') FROM editais WHERE now()<deadline ORDER BY id DESC"""
cursor.execute(consulta)
linhas = cursor.fetchall()
print(linhas)
cursor.close()
conn.close()

