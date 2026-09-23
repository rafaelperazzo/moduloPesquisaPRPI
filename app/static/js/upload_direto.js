/*
 * Upload direto do navegador para o S3 (migracao.s3.md, fase 3).
 *
 * Em formulários com data-upload-direto="<submissoes|docs_indicacoes>" e data-url-upload, cada
 * <input type="file"> listado em data-campos é enviado ao S3 antes do submit, por uma URL assinada
 * (POST) pedida ao app. Um arquivo enviado vira o campo oculto <campo>_s3, e o input é desativado
 * para o arquivo não ir de novo ao app. Qualquer falha (dev, tipo não aceito, rede, CORS) deixa o
 * input como está: o formulário segue com o envio tradicional pelo app.
 */
(function () {
  'use strict';

  function csrf(form) {
    var campo = form.querySelector('input[name="csrf_token"]');
    return campo ? campo.value : '';
  }

  function statusDe(entrada) {
    var status = entrada.parentNode.querySelector('.upload-direto-status[data-campo="' + entrada.name + '"]');
    if (!status) {
      status = document.createElement('span');
      status.className = 'upload-direto-status block mt-1 text-xs text-gray-500';
      status.setAttribute('data-campo', entrada.name);
      entrada.insertAdjacentElement('afterend', status);
    }
    return status;
  }

  function arquivosParaEnviar(form) {
    var campos = (form.dataset.campos || '').split(',');
    return Array.prototype.filter.call(form.querySelectorAll('input[type="file"]'), function (entrada) {
      return campos.indexOf(entrada.name) >= 0 && !entrada.disabled && entrada.files && entrada.files.length === 1;
    });
  }

  function pedirUrl(form, entrada, arquivo) {
    return fetch(form.dataset.urlUpload, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf(form)},
      body: JSON.stringify({
        tipo: form.dataset.uploadDireto,
        campo: entrada.name,
        idProjeto: form.dataset.idProjeto || '',
        tamanho: arquivo.size,
        content_type: arquivo.type
      })
    }).then(function (resposta) {
      if (!resposta.ok) {
        throw new Error('url_upload ' + resposta.status);
      }
      return resposta.json();
    });
  }

  function postarNoS3(dados, arquivo, status) {
    return new Promise(function (ok, falha) {
      var corpo = new FormData();
      Object.keys(dados.fields).forEach(function (chave) {
        corpo.append(chave, dados.fields[chave]);
      });
      corpo.append('file', arquivo); // o S3 exige o arquivo como último campo
      var xhr = new XMLHttpRequest();
      xhr.open('POST', dados.url);
      xhr.upload.onprogress = function (e) {
        if (e.lengthComputable) {
          status.textContent = 'Enviando ' + arquivo.name + ': ' + Math.round(100 * e.loaded / e.total) + '%';
        }
      };
      xhr.onload = function () {
        if (xhr.status >= 200 && xhr.status < 300) {
          ok();
        } else {
          falha(new Error('S3 ' + xhr.status));
        }
      };
      xhr.onerror = function () { falha(new Error('rede')); };
      xhr.send(corpo);
    });
  }

  function enviarUm(form, entrada) {
    var arquivo = entrada.files[0];
    var status = statusDe(entrada);
    status.textContent = 'Enviando ' + arquivo.name + '...';
    return pedirUrl(form, entrada, arquivo)
      .then(function (dados) {
        return postarNoS3(dados, arquivo, status).then(function () { return dados.nome; });
      })
      .then(function (nome) {
        var oculto = document.createElement('input');
        oculto.type = 'hidden';
        oculto.name = entrada.name + '_s3';
        oculto.value = nome;
        oculto.className = 'upload-direto-oculto';
        form.appendChild(oculto);
        entrada.disabled = true;
        status.textContent = 'Arquivo enviado: ' + arquivo.name;
      })
      .catch(function () {
        status.textContent = ''; // segue pelo envio tradicional, junto com o formulário
      });
  }

  function botoes(form, desativar) {
    form.querySelectorAll('[type="submit"]').forEach(function (botao) {
      botao.disabled = desativar;
    });
  }

  function restaurar(form) {
    form.querySelectorAll('.upload-direto-oculto').forEach(function (oculto) { oculto.remove(); });
    form.querySelectorAll('input[type="file"]').forEach(function (entrada) { entrada.disabled = false; });
    form.querySelectorAll('.upload-direto-status').forEach(function (status) { status.textContent = ''; });
    delete form.dataset.enviando;
    botoes(form, false);
  }

  document.querySelectorAll('form[data-upload-direto]').forEach(function (form) {
    form.addEventListener('submit', function (evento) {
      // Validações do próprio formulário (onsubmit) rodam antes e podem cancelar o envio
      if (evento.defaultPrevented) {
        return;
      }
      var entradas = arquivosParaEnviar(form);
      if (entradas.length === 0) {
        return;
      }
      evento.preventDefault();
      if (form.dataset.enviando) {
        return;
      }
      form.dataset.enviando = '1';
      botoes(form, true);
      entradas.reduce(function (anterior, entrada) {
        return anterior.then(function () { return enviarUm(form, entrada); });
      }, Promise.resolve()).then(function () {
        form.submit(); // não dispara o evento submit de novo
      });
    });
  });

  // Ao voltar para a página pelo histórico, o formulário pode reaparecer com inputs desativados
  window.addEventListener('pageshow', function (evento) {
    if (evento.persisted) {
      document.querySelectorAll('form[data-upload-direto]').forEach(restaurar);
    }
  });
})();
