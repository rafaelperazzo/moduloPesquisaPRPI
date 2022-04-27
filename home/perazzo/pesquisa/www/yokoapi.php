<?php

$user = "webapi";
$pass = "h*iVQ$4Bj2^Sp3";
$db = "pesquisa";
$host = "localhost";

//$siape = "2315016";
//$senha = "zyzzSpUC";

$siape = $_POST['siape'];
$senha = $_POST['senha'];

$conexao = mysqli_connect($host,$user,$pass) or die("Erro ao conectar ao BD");
mysqli_select_db($conexao,$db);
$query = "SELECT * FROM users WHERE username='$siape' AND password='$senha'";

$result = mysqli_query($conexao,$query);

$dados = array();

if (mysqli_num_rows($result)>0) {
    $query = "SELECT indicacoes.id,indicacoes.nome,DATE_FORMAT(indicacoes.inicio,'%d/%m/%Y') as inicio,IF(indicacoes.fomento=0,'UFCA',IF(indicacoes.fomento=1,'CNPq','FUNCAP')) as fomento,IF(indicacoes.tipo_de_vaga=0,'VOLUNTÁRIO','BOLSISTA') as tipo,DATE_FORMAT(indicacoes.fim,'%d/%m/%Y') as fim,IF(indicacoes.modalidade=1,'PIBIC',IF(indicacoes.modalidade=2,'PIBITI','PIBIC-EM')) as modalidade,
    (SELECT GROUP_CONCAT(CONCAT_WS('/',mes,ano) SEPARATOR '<BR><BR>') FROM frequencias WHERE frequencias.idIndicacao=indicacoes.id) as enviadas, editalProjeto.titulo
    FROM indicacoes,editalProjeto
    WHERE editalProjeto.id=indicacoes.idProjeto AND indicacoes.fim>NOW() AND editalProjeto.siape=2315016 ORDER BY indicacoes.tipo_de_vaga,editalProjeto.titulo,indicacoes.nome ";
    $result = mysqli_query($conexao,$query);
    while($linha=mysqli_fetch_array($result)) {
        $id = $linha['id'];
        $nome = $linha['nome'];
        $titulo = $linha['titulo'];
        $inicio = $linha['inicio'];
        $fim = $linha['fim'];
        $row = array("id"=>$id,"nome"=>$nome,"inicio"=>$inicio,"fim"=>$fim,"titulo"=>$titulo);
        //echo json_encode($row);
        //print("<BR>");
        $dados[] = $row;
    } 
}


//$dados = array("campo1 " => "Ola mundo", "campo2" => "valor 2");
echo (json_encode($dados));

?>