from pathlib import Path

import pymupdf

PASTA = Path(__file__).resolve().parent.parent / "documentos"
FONTES_WINDOWS = Path("C:/Windows/Fonts")
MARGEM, LARGURA, ALTURA = 60, 595, 842

DOCUMENTOS = {
    "Movimentos e Forcas.pdf": ("Movimentos e Forças — Texto de apoio", [
        [
            ("t", "1. Movimento e repouso"),
            ("p", "Um corpo está em movimento quando a sua posição varia ao longo do tempo em relação a um referencial. Se a posição não varia, o corpo está em repouso em relação a esse referencial. Por isso, movimento e repouso são conceitos relativos: um passageiro sentado num comboio está em repouso em relação ao banco, mas em movimento em relação à estação."),
            ("p", "O referencial é o corpo, ou conjunto de corpos, que se toma como referência para descrever o movimento. A trajetória é a linha formada pelas sucessivas posições ocupadas pelo corpo. Se a trajetória for uma linha reta, o movimento diz-se retilíneo; se for uma linha curva, diz-se curvilíneo."),
            ("t", "2. Distância percorrida e rapidez média"),
            ("p", "A distância percorrida (d) é o comprimento da trajetória descrita pelo corpo e é sempre um valor positivo. No Sistema Internacional (SI), a distância exprime-se em metros (m) e o tempo em segundos (s)."),
            ("p", "A rapidez média (rm) indica a distância percorrida por unidade de tempo e calcula-se dividindo a distância percorrida pelo intervalo de tempo gasto: rm = d / Δt. A unidade SI de rapidez média é o metro por segundo (m/s). Por exemplo, um ciclista que percorre 1200 m em 4 minutos (240 s) tem uma rapidez média de 5 m/s."),
            ("p", "A velocidade é uma grandeza vetorial: além do valor, tem direção e sentido. Num automóvel, o velocímetro indica o valor da velocidade em cada instante, ou seja, a rapidez instantânea."),
        ],
        [
            ("t", "3. Aceleração"),
            ("p", "A aceleração média (am) mede a rapidez com que a velocidade de um corpo varia. Calcula-se pela expressão am = Δv / Δt, em que Δv é a variação da velocidade e Δt o intervalo de tempo. A unidade SI de aceleração é o metro por segundo quadrado (m/s²)."),
            ("p", "No movimento retilíneo uniforme, a velocidade é constante e a aceleração é nula. No movimento retilíneo uniformemente acelerado, o valor da velocidade aumenta sempre a mesma quantidade em intervalos de tempo iguais; no movimento uniformemente retardado, o valor da velocidade diminui de forma constante."),
            ("p", "Num gráfico velocidade-tempo, a área entre a linha do gráfico e o eixo dos tempos é numericamente igual à distância percorrida pelo corpo nesse intervalo de tempo."),
            ("t", "4. Segurança rodoviária"),
            ("p", "A distância de segurança é a distância mínima que um condutor deve manter em relação ao veículo da frente para conseguir parar sem colidir. A distância de paragem é a soma da distância de reação com a distância de travagem."),
            ("p", "A distância de reação é a distância percorrida durante o tempo de reação, isto é, desde que o condutor vê o obstáculo até começar a travar. O tempo de reação aumenta com o consumo de álcool, drogas ou medicamentos, com o cansaço e com distrações como o uso do telemóvel."),
            ("p", "A distância de travagem é a distância percorrida desde que o condutor começa a travar até o veículo parar. Aumenta com a velocidade do veículo, com a massa do veículo e com o mau estado dos pneus, dos travões ou do piso (por exemplo, piso molhado ou com gelo)."),
        ],
        [
            ("t", "5. Forças e as Leis de Newton"),
            ("p", "Uma força resulta da interação entre dois corpos e pode alterar o estado de repouso ou de movimento de um corpo, ou provocar deformações. A força é uma grandeza vetorial, caracterizada pelo ponto de aplicação, pela direção, pelo sentido e pela intensidade. A unidade SI de força é o newton (N) e a intensidade de uma força pode ser medida com um dinamómetro."),
            ("p", "Primeira Lei de Newton (Lei da Inércia): se a resultante das forças que atuam num corpo for nula, o corpo permanece em repouso ou em movimento retilíneo uniforme. A inércia é a tendência de um corpo para manter o seu estado de repouso ou de movimento; quanto maior a massa, maior a inércia. É por isso que, numa travagem brusca, os passageiros são projetados para a frente e devem usar o cinto de segurança."),
            ("p", "Segunda Lei de Newton (Lei Fundamental da Dinâmica): a resultante das forças que atuam num corpo é diretamente proporcional à aceleração que este adquire, sendo a constante de proporcionalidade a massa do corpo: F = m × a. A aceleração tem sempre a mesma direção e o mesmo sentido da força resultante."),
            ("p", "Terceira Lei de Newton (Lei da Ação-Reação): quando um corpo exerce uma força sobre outro, este exerce sobre o primeiro uma força com a mesma intensidade e a mesma direção, mas de sentido oposto. As forças de um par ação-reação atuam em corpos diferentes e, por isso, não se anulam."),
            ("p", "O peso (P) é a força com que a Terra atrai os corpos e calcula-se por P = m × g, em que g é a aceleração da gravidade (aproximadamente 9,8 m/s² à superfície da Terra). A massa de um corpo é a mesma em qualquer lugar, mas o peso depende do local onde o corpo se encontra."),
        ],
    ]),
    "Reacoes Quimicas.pdf": ("Reações Químicas — Texto de apoio", [
        [
            ("t", "1. Transformações físicas e químicas"),
            ("p", "Nas transformações físicas, as substâncias mantêm-se, mudando apenas o seu estado físico, a forma ou o tamanho. A fusão do gelo e a dissolução do açúcar em água são exemplos de transformações físicas."),
            ("p", "Nas transformações químicas, também chamadas reações químicas, há formação de novas substâncias. As substâncias iniciais chamam-se reagentes e as substâncias que se formam chamam-se produtos da reação."),
            ("p", "Alguns sinais que indicam que ocorreu uma reação química são: a mudança de cor, a libertação de um gás (efervescência), a formação de um sólido insolúvel (precipitado), a variação de temperatura e a emissão de luz."),
            ("t", "2. Equações químicas"),
            ("p", "Uma reação química pode ser representada por uma equação química. Os reagentes escrevem-se à esquerda e os produtos à direita, separados por uma seta, que se lê \"dá origem a\". Por exemplo: metano + oxigénio → dióxido de carbono + água."),
            ("p", "Numa equação química escrita com fórmulas químicas, indica-se também o estado físico de cada substância: (s) sólido, (l) líquido, (g) gasoso e (aq) solução aquosa. Exemplo: CH4 (g) + 2 O2 (g) → CO2 (g) + 2 H2O (l)."),
        ],
        [
            ("t", "3. Lei de Lavoisier"),
            ("p", "A Lei de Lavoisier, ou Lei da Conservação da Massa, afirma que, numa reação química que ocorra num sistema fechado, a massa total dos reagentes é igual à massa total dos produtos. Esta lei costuma resumir-se na frase: \"Na Natureza nada se cria, nada se perde, tudo se transforma.\""),
            ("p", "Isto acontece porque, numa reação química, os átomos não são criados nem destruídos: apenas se reorganizam, formando novas substâncias. Por esse motivo, as equações químicas têm de ser acertadas, ou seja, o número de átomos de cada elemento tem de ser igual nos reagentes e nos produtos. Exemplo de uma equação acertada: 2 H2 (g) + O2 (g) → 2 H2O (l)."),
            ("t", "4. Tipos de reações químicas"),
            ("p", "Reações de combustão: são reações entre um combustível e um comburente (geralmente o oxigénio do ar), com libertação de energia sob a forma de calor e luz. Para que uma combustão se inicie é necessária uma energia de ativação, por exemplo uma faísca. O triângulo do fogo representa os três elementos necessários: combustível, comburente e energia de ativação."),
            ("p", "Reações ácido-base: ocorrem entre um ácido e uma base, formando um sal e água. O caráter químico de uma solução pode ser identificado com indicadores ácido-base: a solução alcoólica de fenolftaleína fica incolor em soluções ácidas e neutras e carmim em soluções básicas; o tornesol fica vermelho em meio ácido e azul em meio básico."),
            ("p", "A escala de pH, a 25 °C, varia de 0 a 14. Uma solução com pH inferior a 7 é ácida, com pH igual a 7 é neutra e com pH superior a 7 é básica. Quanto menor o pH, mais ácida é a solução."),
            ("p", "Reações de precipitação: ocorrem quando se misturam duas soluções aquosas e se forma um sal pouco solúvel, que aparece como um sólido chamado precipitado."),
        ],
        [
            ("t", "5. Velocidade das reações químicas"),
            ("p", "A velocidade de uma reação química indica a rapidez com que os reagentes se transformam em produtos. Segundo a teoria das colisões, para que uma reação ocorra, as partículas dos reagentes têm de colidir com energia suficiente e com a orientação adequada."),
            ("p", "Fatores que influenciam a velocidade das reações: a concentração dos reagentes (maior concentração, mais colisões e reação mais rápida); a temperatura (temperatura mais elevada, partículas com mais energia e reação mais rápida); o estado de divisão dos reagentes sólidos (quanto mais dividido, maior a superfície de contacto e mais rápida a reação); a presença de catalisadores, que aumentam a velocidade da reação sem serem consumidos; e a luz, no caso das reações fotoquímicas."),
            ("p", "Os inibidores são substâncias que diminuem a velocidade das reações. São usados, por exemplo, como conservantes nos alimentos, para retardar a sua degradação. Pelo contrário, as enzimas são catalisadores biológicos que aceleram reações no organismo, como as da digestão."),
        ],
    ]),
    "Atomos e Tabela Periodica.pdf": ("Átomos e Tabela Periódica — Texto de apoio", [
        [
            ("t", "1. Constituição do átomo"),
            ("p", "O átomo é constituído por um núcleo, muito pequeno e denso, onde se encontram os protões (com carga elétrica positiva) e os neutrões (sem carga elétrica), e por uma nuvem eletrónica, onde se movem os eletrões (com carga elétrica negativa). Num átomo, o número de protões é igual ao número de eletrões, por isso o átomo é eletricamente neutro."),
            ("p", "O número atómico (Z) é o número de protões existentes no núcleo de um átomo e identifica o elemento químico. O número de massa (A) é a soma do número de protões com o número de neutrões. Átomos do mesmo elemento com diferente número de neutrões chamam-se isótopos."),
            ("p", "Quando um átomo perde eletrões, forma-se um ião positivo (catião); quando ganha eletrões, forma-se um ião negativo (anião). Por exemplo, o átomo de sódio perde um eletrão e origina o ião Na+, enquanto o átomo de cloro ganha um eletrão e origina o ião Cl-."),
            ("t", "2. Distribuição eletrónica"),
            ("p", "Segundo o modelo da nuvem eletrónica, os eletrões distribuem-se por níveis de energia. No primeiro nível cabem no máximo 2 eletrões e no segundo nível cabem no máximo 8. Por exemplo, a distribuição eletrónica do sódio (Z = 11) é 2-8-1."),
            ("p", "Os eletrões do último nível de energia chamam-se eletrões de valência. São estes eletrões que determinam o comportamento químico dos elementos."),
        ],
        [
            ("t", "3. Tabela Periódica"),
            ("p", "Na Tabela Periódica atual, os elementos químicos estão organizados por ordem crescente de número atómico, em 18 grupos (colunas) e 7 períodos (linhas). Elementos do mesmo grupo têm o mesmo número de eletrões de valência e, por isso, propriedades químicas semelhantes."),
            ("p", "Para os elementos representativos, o número do período corresponde ao número de níveis de energia ocupados por eletrões, e o número de eletrões de valência corresponde ao algarismo das unidades do número do grupo (por exemplo, os elementos do grupo 17 têm 7 eletrões de valência)."),
            ("p", "Metais alcalinos (grupo 1): têm um eletrão de valência, que perdem com facilidade, formando iões monopositivos. Reagem violentamente com a água, formando hidróxidos (soluções básicas) e libertando hidrogénio. Por serem muito reativos, conservam-se em petróleo ou parafina líquida."),
            ("p", "Metais alcalinoterrosos (grupo 2): têm dois eletrões de valência e formam iões dipositivos. São reativos, mas menos do que os metais alcalinos do mesmo período."),
            ("p", "Halogéneos (grupo 17): têm sete eletrões de valência e tendem a captar um eletrão, formando iões mononegativos. São muito reativos e formam moléculas diatómicas, como o cloro (Cl2)."),
            ("p", "Gases nobres (grupo 18): têm o último nível de energia completo, o que os torna muito estáveis e muito pouco reativos. Existem na Natureza como átomos isolados. O hélio é usado em balões e o néon em reclamos luminosos."),
            ("p", "Os metais são, em geral, bons condutores do calor e da corrente elétrica, têm brilho metálico e são maleáveis. Os não metais são, em geral, maus condutores e quebradiços no estado sólido."),
        ],
    ]),
}


def _fontes():
    normal, negrito = FONTES_WINDOWS / "arial.ttf", FONTES_WINDOWS / "arialbd.ttf"
    if normal.exists() and negrito.exists():
        return {"t": ("arialbd", str(negrito)), "p": ("arial", str(normal))}
    return {"t": ("hebo", None), "p": ("helv", None)}


def _quebrar(texto, fonte, tamanho, largura):
    linhas, atual = [], ""
    for palavra in texto.split():
        tentativa = f"{atual} {palavra}".strip()
        if fonte.text_length(tentativa, fontsize=tamanho) > largura and atual:
            linhas.append(atual)
            atual = palavra
        else:
            atual = tentativa
    return linhas + [atual]


def gerar(nome, titulo, paginas):
    fontes = _fontes()
    medidas = {k: pymupdf.Font(fontfile=f) if f else pymupdf.Font(n) for k, (n, f) in fontes.items()}
    doc = pymupdf.open()
    for num, blocos in enumerate(paginas, start=1):
        pag = doc.new_page(width=LARGURA, height=ALTURA)
        y = MARGEM
        if num == 1:
            pag.insert_text((MARGEM, y), titulo, fontsize=17, fontname=fontes["t"][0], fontfile=fontes["t"][1])
            y += 40
        for tipo, texto in blocos:
            tamanho = 13 if tipo == "t" else 11
            nome_fonte, ficheiro = fontes[tipo]
            for linha in _quebrar(texto, medidas[tipo], tamanho, LARGURA - 2 * MARGEM):
                pag.insert_text((MARGEM, y), linha, fontsize=tamanho, fontname=nome_fonte, fontfile=ficheiro)
                y += tamanho * 1.45
            y += tamanho * 0.9
        pag.insert_text((LARGURA / 2 - 3, ALTURA - 30), str(num), fontsize=9,
                        fontname=fontes["p"][0], fontfile=fontes["p"][1])
    doc.subset_fonts()
    PASTA.mkdir(exist_ok=True)
    doc.save(PASTA / nome, garbage=3, deflate=True)
    print(f"criado: documentos/{nome} ({len(paginas)} páginas)")


if __name__ == "__main__":
    for nome, (titulo, paginas) in DOCUMENTOS.items():
        gerar(nome, titulo, paginas)
