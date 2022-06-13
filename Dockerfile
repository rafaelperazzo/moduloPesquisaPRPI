FROM debian:10
ENV TZ=America/Fortaleza
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN useradd -m perazzo
RUN apt-get update
RUN apt-get install -y python python-pip python-dev build-essential g++ python-bs4 python-soupsieve libmariadbclient-dev libmariadb-dev-compat libmariadb-dev wkhtmltopdf
COPY requirements.txt ./
RUN pip install --upgrade pip
#RUN pip install --no-cache-dir -r requirements.txt
RUN pip install numpy==1.16.6 pandas==0.24.2 matplotlib==2.2.5 werkzeug==0.16.1 Flask==1.1.2 lxml==4.3.2 mysqlclient==1.4.6 requests==2.25.0 Flask-HTTPAuth==4.2.0 Flask-Mail==0.9.1 Flask-Uploads==0.2.1 pdfkit==0.6.1 waitress==1.4.4
RUN pip install unidecode==1.1.1
RUN pip install zeep
EXPOSE 80
CMD python /home/perazzo/pesquisa/pesquisa.py
