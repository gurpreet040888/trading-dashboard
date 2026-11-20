// Explicit ISIN links avoid matching similarly named securities.
const holdingTickers = {
  INE021A01026:'ASIANPAINT.NS', INE486A01021:'CESC.NS', INE016A01026:'DABUR.NS',
  INE066A01021:'EICHERMOT.NS', INE040A01034:'HDFCBANK.NS', INE030A01027:'HINDUNILVR.NS',
  INE242A01010:'IOC.NS', INE009A01021:'INFY.NS', INE758E01017:'JIOFIN.NS',
  INE239A01024:'NESTLEIND.NS', INE848E01016:'NHPC.NS', INE733E01010:'NTPC.NS',
  INE318A01026:'PIDILITIND.NS', INE002A01018:'RELIANCE.NS', INE425Y01011:'RPSGVENT.NS',
  INE803H01014:'RUCHIRA.NS', INE020801028:'SPENCERS.NS', INE467B01029:'TCS.NS',
  INE280A01028:'TITAN.NS', INE079A01024:'AMBUJACEM.NS', INE029A01011:'BPCL.NS',
  INE397D01024:'BHARTIARTL.NS', INE736A01011:'CDSL.NS', INE522F01014:'COALINDIA.NS',
  INE066F01020:'HAL.NS', INE0GSL01024:'HPAL.NS', INE335Y01020:'IRCTC.NS',
  INE053F01010:'IRFC.NS', INE154A01025:'ITC.NS', INE018A01030:'LT.NS',
  INE745G01035:'MCX.NS', INE745G01043:'MCX.NS', INE260D01016:'OLECTRA.NS',
  INE752E01010:'POWERGRID.NS', INE020B01018:'REC.NS', INE0N2P01017:'RISHABH.NS',
  INE916U01025:'SHEELA.NS', INE232A01011:'SHREDIGCEM.NS', INE081A01020:'TATASTEEL.NS',
  INE849A01020:'TRENT.NS', INE415A01038:'AGI.NS', INE930P01018:'ANURAS.NS',
  INE600Y01019:'DYNAMIC.NS', INE138Y01010:'KFINTECH.NS', INE265B01019:'NITTA.NS',
  INE0AE001013:'VPRPL.NS'
};
let holdingQuotes = new Map();
let holdingPrices = {};
let holdingMarketState = 'Loading market data…';
let holdingMarketRequest;
let detailPriceChart;
let detailStatementChart;

function holdingMarketMetrics(holding){
    const quote = holdingQuotes.get(holdingTickers[holding.isin]);
    const cmp = Number.isFinite(quote?.current) && quote.current>0 ? quote.current : null;
    const average = Number.isFinite(quote?.buy_price) && quote.buy_price>0 ? quote.buy_price : null;
    return {
        cmp, average, date:quote?.price_date || 'Unavailable',
        gain:cmp!=null && average!=null ? (cmp-average)*holding.qty : null
    };
}

function updateHoldingDetail(list){
    const select = document.getElementById('holdingSelect');
    const previous = select.value;
    select.replaceChildren(...[...list].sort((a,b)=>a.name.localeCompare(b.name)).map(holding=>{
        const option = document.createElement('option');
        option.value = holding.isin;
        const ticker = holdingTickers[holding.isin];
        option.textContent = (ticker ? ticker+' · ' : '')+holding.name;
        return option;
    }));
    if(list.some(holding=>holding.isin===previous)) select.value = previous;
    renderHoldingDetail();
}

async function loadHoldingMarketData(){
    // Cache one in-flight request. Reopening a statement does not duplicate downloads.
    if(holdingMarketRequest) return holdingMarketRequest;
    holdingMarketRequest = (async ()=>{
        const read = async path=>{
            const response = await fetch(path,{cache:'no-store'});
            if(!response.ok) throw new Error('Market file unavailable');
            return response.json();
        };
        const [quotes,prices] = await Promise.allSettled([
            read('../data.json'), read('../historical_prices.json')
        ]);
        holdingQuotes = new Map((Array.isArray(quotes.value) ? quotes.value : []).map(quote=>[quote.ticker,quote]));
        holdingPrices = prices.status==='fulfilled' && prices.value && typeof prices.value==='object' ? prices.value : {};
        holdingMarketState = quotes.status==='rejected' || prices.status==='rejected'
            ? 'Some market data could not be loaded. Reload the page to retry.' : '';
        if(model){
            renderHoldingHistory(filteredList());
            renderHoldingDetail();
        }
    })();
    return holdingMarketRequest;
}

function renderHoldingDetail(){
    if(detailPriceChart) detailPriceChart.destroy();
    if(detailStatementChart) detailStatementChart.destroy();
    detailPriceChart = detailStatementChart = null;
    const holding = model.list.find(item=>item.isin===document.getElementById('holdingSelect').value);
    const body = document.querySelector('#holdingSummary tbody');
    body.replaceChildren();
    if(!holding){
        document.getElementById('priceHistoryStatus').textContent = 'No holding selected.';
        return;
    }
    const ticker = holdingTickers[holding.isin];
    const quote = holdingQuotes.get(ticker);
    const market = holdingMarketMetrics(holding);
    const suggestion = signal(holding);
    const score = quote?.ai_score;
    const technical = !(quote?.current>0) || !Number.isFinite(score) ? 'Unavailable' :
        score>=3 ? 'Strong Buy' : score>=1 ? 'Buy' :
        score<=-3 ? 'Strong Sell' : score<=-1 ? 'Sell' : 'Hold';
    const quoteAge = Date.now()-Date.parse(quote?.price_date);
    const historical = !Number.isFinite(quoteAge) || quoteAge<0 || quoteAge>7*86400000;
    const summaryRows = [
        ['Holding',holding.name],
        ['Ticker / ISIN',(ticker || 'Ticker not linked')+' · '+holding.isin],
        ['Latest statement',holding.dateText],
        ['Holding value',nf.format(holding.total)],
        ['Quantity',quantityFormat.format(holding.qty)],
        ['CMP',market.cmp==null ? 'Unavailable' : priceFormat.format(market.cmp)],
        ['Average Price',market.average==null ? 'Unavailable' : priceFormat.format(market.average)],
        ['Absolute gain/loss',market.gain==null ? 'Unavailable' : nf.format(market.gain)],
        ['Gain/loss basis','Latest quote × latest statement quantity, less portfolio buy price × that quantity'],
        ['Estimated XIRR',holding.xirr==null ? 'Insufficient history' : (holding.xirr*100).toFixed(1)+'%'],
        ['AI suggestion',suggestion.label],
        ['Suggestion evidence',suggestion.reason],
        ['Technical signal',technical+(quote && historical ? ' · Historical' : '')],
        ['Technical evidence',Array.isArray(quote?.reasons) ? quote.reasons.join(' · ') :
            ticker ? holdingMarketState || 'Quote unavailable for this ticker.' : 'No linked ticker in the dashboard data.'],
        ['Quote date',quote?.price_date || 'Unavailable']
    ];
    summaryRows.forEach(([label,value])=>{
        const row = document.createElement('tr');
        const heading = document.createElement('th');
        heading.scope = 'row';
        heading.textContent = label;
        const cell = document.createElement('td');
        cell.textContent = value;
        if(label==='AI suggestion'){
            const pill = document.createElement('span');
            pill.className = 'pill '+suggestion.cls;
            pill.textContent = value;
            cell.replaceChildren(pill);
        }
        if(label==='Technical signal') cell.className = technical.includes('Buy') ? 'positive' :
            technical.includes('Sell') ? 'negative' : 'neutral';
        row.append(heading,cell);
        body.append(row);
    });
    const history = holdingPrices[ticker];
    const points = Array.isArray(history?.dates) && Array.isArray(history?.prices)
        ? history.dates.map((date,index)=>({date,price:history.prices[index]}))
            .filter(point=>Number.isFinite(point.price) && point.price>0) : [];
    const status = document.getElementById('priceHistoryStatus');
    status.textContent = points.length
        ? ticker+' · '+points[0].date+' to '+points.at(-1).date+' · adjusted daily close (₹)'
        : ticker ? holdingMarketState || 'Price history unavailable for '+ticker+'.'
            : 'This holding has no linked ticker. Statement history is shown alongside.';
    if(points.length){
        detailPriceChart = new Chart(document.getElementById('holdingPriceChart'),{
            type:'line',
            data:{labels:points.map(point=>point.date),datasets:[{
                label:'Adjusted close (₹)',data:points.map(point=>point.price),
                borderColor:'#2a5d9f',borderWidth:2,pointRadius:0,pointHitRadius:8
            }]},
            options:{responsive:true,maintainAspectRatio:false,animation:false,
                interaction:{mode:'index',intersect:false},
                plugins:{legend:{display:false}},
                scales:{x:{ticks:{maxTicksLimit:6}},y:{title:{display:true,text:'Price (₹)'}}}}
        });
    }
    detailStatementChart = new Chart(document.getElementById('holdingStatementChart'),{
        type:'line',
        data:{labels:model.dates,datasets:[
            {label:'Holding value (₹)',data:model.dates.map(date=>model.grouped.get(holding.isin+'|'+date)?.total ?? null),
                borderColor:'#1f6f54',yAxisID:'value',pointRadius:3,spanGaps:false},
            {label:'Quantity / units',data:model.dates.map(date=>model.grouped.get(holding.isin+'|'+date)?.qty ?? null),
                borderColor:'#2a5d9f',yAxisID:'quantity',pointRadius:3,spanGaps:false}
        ]},
        options:{responsive:true,maintainAspectRatio:false,animation:false,
            interaction:{mode:'index',intersect:false},
            scales:{
                x:{ticks:{maxTicksLimit:6}},
                value:{position:'left',title:{display:true,text:'Value (₹)'},ticks:{callback:value=>nf.format(value)}},
                quantity:{position:'right',title:{display:true,text:'Quantity / units'},grid:{drawOnChartArea:false}}
            }}
    });
}
document.getElementById('holdingSelect').addEventListener('change',renderHoldingDetail);
