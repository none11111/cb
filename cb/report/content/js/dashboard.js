/*
   Licensed to the Apache Software Foundation (ASF) under one or more
   contributor license agreements.  See the NOTICE file distributed with
   this work for additional information regarding copyright ownership.
   The ASF licenses this file to You under the Apache License, Version 2.0
   (the "License"); you may not use this file except in compliance with
   the License.  You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
*/
var showControllersOnly = false;
var seriesFilter = "";
var filtersOnlySampleSeries = true;

/*
 * Add header in statistics table to group metrics by category
 * format
 *
 */
function summaryTableHeader(header) {
    var newRow = header.insertRow(-1);
    newRow.className = "tablesorter-no-sort";
    var cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 1;
    cell.innerHTML = "Requests";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 3;
    cell.innerHTML = "Executions";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 7;
    cell.innerHTML = "Response Times (ms)";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 1;
    cell.innerHTML = "Throughput";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 2;
    cell.innerHTML = "Network (KB/sec)";
    newRow.appendChild(cell);
}

/*
 * Populates the table identified by id parameter with the specified data and
 * format
 *
 */
function createTable(table, info, formatter, defaultSorts, seriesIndex, headerCreator) {
    var tableRef = table[0];

    // Create header and populate it with data.titles array
    var header = tableRef.createTHead();

    // Call callback is available
    if(headerCreator) {
        headerCreator(header);
    }

    var newRow = header.insertRow(-1);
    for (var index = 0; index < info.titles.length; index++) {
        var cell = document.createElement('th');
        cell.innerHTML = info.titles[index];
        newRow.appendChild(cell);
    }

    var tBody;

    // Create overall body if defined
    if(info.overall){
        tBody = document.createElement('tbody');
        tBody.className = "tablesorter-no-sort";
        tableRef.appendChild(tBody);
        var newRow = tBody.insertRow(-1);
        var data = info.overall.data;
        for(var index=0;index < data.length; index++){
            var cell = newRow.insertCell(-1);
            cell.innerHTML = formatter ? formatter(index, data[index]): data[index];
        }
    }

    // Create regular body
    tBody = document.createElement('tbody');
    tableRef.appendChild(tBody);

    var regexp;
    if(seriesFilter) {
        regexp = new RegExp(seriesFilter, 'i');
    }
    // Populate body with data.items array
    for(var index=0; index < info.items.length; index++){
        var item = info.items[index];
        if((!regexp || filtersOnlySampleSeries && !info.supportsControllersDiscrimination || regexp.test(item.data[seriesIndex]))
                &&
                (!showControllersOnly || !info.supportsControllersDiscrimination || item.isController)){
            if(item.data.length > 0) {
                var newRow = tBody.insertRow(-1);
                for(var col=0; col < item.data.length; col++){
                    var cell = newRow.insertCell(-1);
                    cell.innerHTML = formatter ? formatter(col, item.data[col]) : item.data[col];
                }
            }
        }
    }

    // Add support of columns sort
    table.tablesorter({sortList : defaultSorts});
}

$(document).ready(function() {

    // Customize table sorter default options
    $.extend( $.tablesorter.defaults, {
        theme: 'blue',
        cssInfoBlock: "tablesorter-no-sort",
        widthFixed: true,
        widgets: ['zebra']
    });

    var data = {"OkPercent": 100.0, "KoPercent": 0.0};
    var dataset = [
        {
            "label" : "FAIL",
            "data" : data.KoPercent,
            "color" : "#FF6347"
        },
        {
            "label" : "PASS",
            "data" : data.OkPercent,
            "color" : "#9ACD32"
        }];
    $.plot($("#flot-requests-summary"), dataset, {
        series : {
            pie : {
                show : true,
                radius : 1,
                label : {
                    show : true,
                    radius : 3 / 4,
                    formatter : function(label, series) {
                        return '<div style="font-size:8pt;text-align:center;padding:2px;color:white;">'
                            + label
                            + '<br/>'
                            + Math.round10(series.percent, -2)
                            + '%</div>';
                    },
                    background : {
                        opacity : 0.5,
                        color : '#000'
                    }
                }
            }
        },
        legend : {
            show : true
        }
    });

    // Creates APDEX table
    createTable($("#apdexTable"), {"supportsControllersDiscrimination": true, "overall": {"data": [0.8650442477876106, 500, 1500, "Total"], "isController": false}, "titles": ["Apdex", "T (Toleration threshold)", "F (Frustration threshold)", "Label"], "items": [{"data": [1.0, 500, 1500, "POST /api/orders/220/update (completed)"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/auth/me"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/admin/login-history"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/218/update (completed)"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/288"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/222/update (paid)"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/222/update (completed)"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/246"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/247"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/284"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/240"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/286"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/my-products"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/auth/login (Buyer)"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/216/update (completed)"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/219/update (paid)"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/224/update (completed)"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/admin/anomaly-detection"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/products"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/admin/products"], "isController": false}, {"data": [0.0, 500, 1500, "POST /api/analyze-product"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/215/update (paid)"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/239"], "isController": false}, {"data": [0.9, 500, 1500, "POST /api/auth/login (Seller)"], "isController": false}, {"data": [0.5, 500, 1500, "POST /api/admin/login"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/277"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/236"], "isController": false}, {"data": [0.9166666666666666, 500, 1500, "POST /api/auth/login"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/275"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/231"], "isController": false}, {"data": [0.85, 500, 1500, "POST /api/product"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/221/update (paid)"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/admin/users"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/307"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/308"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/309"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/303"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/304"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/219/update (completed)"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/305"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/306"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/300"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/223"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/267"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/301"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/221/update (completed)"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/302"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/223/update (completed)"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/216/update (paid)"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/224/update (paid)"], "isController": false}, {"data": [0.0, 500, 1500, "POST /api/generate-all-copies"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/215/update (completed)"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/217/update (completed)"], "isController": false}, {"data": [1.0, 500, 1500, "GET /"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/220/update (paid)"], "isController": false}, {"data": [0.0, 500, 1500, "POST /api/generate-copy"], "isController": false}, {"data": [0.0, 500, 1500, "POST /api/analyze-image"], "isController": false}, {"data": [1.0, 500, 1500, "PUT /api/my-products/edit/300"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/218"], "isController": false}, {"data": [1.0, 500, 1500, "PUT /api/my-products/edit/303"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/256"], "isController": false}, {"data": [1.0, 500, 1500, "PUT /api/my-products/edit/304"], "isController": false}, {"data": [1.0, 500, 1500, "PUT /api/my-products/edit/301"], "isController": false}, {"data": [1.0, 500, 1500, "PUT /api/my-products/edit/302"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/orders"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/217/update (paid)"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/223/update (paid)"], "isController": false}, {"data": [1.0, 500, 1500, "POST /api/orders/218/update (paid)"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/product/293"], "isController": false}, {"data": [0.0, 500, 1500, "POST /api/detect-product"], "isController": false}, {"data": [1.0, 500, 1500, "GET /api/search"], "isController": false}, {"data": [1.0, 500, 1500, "PUT /api/my-products/edit/307"], "isController": false}, {"data": [1.0, 500, 1500, "PUT /api/my-products/edit/308"], "isController": false}, {"data": [1.0, 500, 1500, "PUT /api/my-products/edit/305"], "isController": false}, {"data": [1.0, 500, 1500, "PUT /api/my-products/edit/306"], "isController": false}, {"data": [1.0, 500, 1500, "PUT /api/my-products/edit/309"], "isController": false}]}, function(index, item){
        switch(index){
            case 0:
                item = item.toFixed(3);
                break;
            case 1:
            case 2:
                item = formatDuration(item);
                break;
        }
        return item;
    }, [[0, 0]], 3);

    // Create statistics table
    createTable($("#statisticsTable"), {"supportsControllersDiscrimination": true, "overall": {"data": ["Total", 226, 0, 0.0, 462.96460176991144, 11, 3656, 174.5, 2304.9, 2748.1999999999975, 3565.8299999999995, 13.13953488372093, 33.54123137718023, 3.6828329396802326], "isController": false}, "titles": ["Label", "#Samples", "FAIL", "Error %", "Average", "Min", "Max", "Median", "90th pct", "95th pct", "99th pct", "Transactions/s", "Received", "Sent"], "items": [{"data": ["POST /api/orders/220/update (completed)", 1, 0, 0.0, 46.0, 46, 46, 46.0, 46.0, 46.0, 46.0, 21.73913043478261, 6.071671195652174, 7.1756114130434785], "isController": false}, {"data": ["GET /api/auth/me", 5, 0, 0.0, 209.0, 107, 397, 179.0, 397.0, 397.0, 397.0, 2.8768699654775607, 1.212555739355581, 0.7107891613924051], "isController": false}, {"data": ["GET /api/admin/login-history", 1, 0, 0.0, 98.0, 98, 98, 98.0, 98.0, 98.0, 98.0, 10.204081632653061, 30.50263073979592, 3.1190210459183674], "isController": false}, {"data": ["POST /api/orders/218/update (completed)", 1, 0, 0.0, 37.0, 37, 37, 37.0, 37.0, 37.0, 37.0, 27.027027027027028, 7.5485641891891895, 8.921030405405405], "isController": false}, {"data": ["GET /api/product/288", 1, 0, 0.0, 196.0, 196, 196, 196.0, 196.0, 196.0, 196.0, 5.1020408163265305, 3.487723214285714, 1.2804926658163265], "isController": false}, {"data": ["POST /api/orders/222/update (paid)", 1, 0, 0.0, 29.0, 29, 29, 29.0, 29.0, 29.0, 29.0, 34.48275862068965, 10.910560344827585, 11.21363146551724], "isController": false}, {"data": ["POST /api/orders/222/update (completed)", 1, 0, 0.0, 37.0, 37, 37, 37.0, 37.0, 37.0, 37.0, 27.027027027027028, 7.5485641891891895, 8.921030405405405], "isController": false}, {"data": ["GET /api/product/246", 1, 0, 0.0, 129.0, 129, 129, 129.0, 129.0, 129.0, 129.0, 7.751937984496124, 5.480862403100775, 1.9455547480620154], "isController": false}, {"data": ["GET /api/product/247", 1, 0, 0.0, 92.0, 92, 92, 92.0, 92.0, 92.0, 92.0, 10.869565217391305, 7.685122282608695, 2.728006114130435], "isController": false}, {"data": ["GET /api/product/284", 1, 0, 0.0, 188.0, 188, 188, 188.0, 188.0, 188.0, 188.0, 5.319148936170213, 3.641331449468085, 1.334981715425532], "isController": false}, {"data": ["GET /api/product/240", 1, 0, 0.0, 30.0, 30, 30, 30.0, 30.0, 30.0, 30.0, 33.333333333333336, 23.567708333333336, 8.365885416666668], "isController": false}, {"data": ["GET /api/product/286", 1, 0, 0.0, 173.0, 173, 173, 173.0, 173.0, 173.0, 173.0, 5.780346820809248, 3.9514089595375728, 1.4507315751445087], "isController": false}, {"data": ["GET /api/my-products", 10, 0, 0.0, 97.6, 18, 266, 58.5, 257.8, 266.0, 266.0, 1.6909029421711192, 2.895506161227596, 0.42437700794724387], "isController": false}, {"data": ["POST /api/auth/login (Buyer)", 10, 0, 0.0, 353.7, 251, 444, 330.0, 443.5, 444.0, 444.0, 1.7367141368530739, 0.9668952435741577, 0.4920124717783953], "isController": false}, {"data": ["POST /api/orders/216/update (completed)", 1, 0, 0.0, 40.0, 40, 40, 40.0, 40.0, 40.0, 40.0, 25.0, 6.982421875, 8.251953125], "isController": false}, {"data": ["POST /api/orders/219/update (paid)", 1, 0, 0.0, 17.0, 17, 17, 17.0, 17.0, 17.0, 17.0, 58.8235294117647, 18.612132352941174, 19.129136029411764], "isController": false}, {"data": ["POST /api/orders/224/update (completed)", 1, 0, 0.0, 30.0, 30, 30, 30.0, 30.0, 30.0, 30.0, 33.333333333333336, 9.309895833333334, 11.002604166666668], "isController": false}, {"data": ["GET /api/admin/anomaly-detection", 1, 0, 0.0, 274.0, 274, 274, 274.0, 274.0, 274.0, 274.0, 3.6496350364963503, 395.23337705291965, 1.129818658759124], "isController": false}, {"data": ["GET /api/products", 20, 0, 0.0, 117.05000000000001, 11, 356, 57.5, 330.7000000000001, 354.95, 356.0, 2.8328611898017, 28.263738270184138, 0.5726584631728046], "isController": false}, {"data": ["GET /api/admin/products", 1, 0, 0.0, 215.0, 215, 215, 215.0, 215.0, 215.0, 215.0, 4.651162790697675, 47.27016715116279, 1.489825581395349], "isController": false}, {"data": ["POST /api/analyze-product", 5, 0, 0.0, 2376.2, 2298, 2520, 2332.0, 2520.0, 2520.0, 2520.0, 1.4801657785671996, 0.8383751480165779, 0.5406074230313795], "isController": false}, {"data": ["POST /api/orders/215/update (paid)", 1, 0, 0.0, 122.0, 122, 122, 122.0, 122.0, 122.0, 122.0, 8.196721311475411, 2.5934938524590163, 2.6655353483606556], "isController": false}, {"data": ["GET /api/product/239", 2, 0, 0.0, 35.5, 22, 49, 35.5, 49.0, 49.0, 49.0, 3.189792663476874, 2.2552830940988837, 0.8005631977671451], "isController": false}, {"data": ["POST /api/auth/login (Seller)", 10, 0, 0.0, 370.0, 223, 594, 336.0, 588.0, 594.0, 594.0, 1.1025358324145536, 0.6115628445424476, 0.24656318908489525], "isController": false}, {"data": ["POST /api/admin/login", 1, 0, 0.0, 688.0, 688, 688, 688.0, 688.0, 688.0, 688.0, 1.4534883720930232, 0.8104900981104651, 0.320789425872093], "isController": false}, {"data": ["GET /api/product/277", 1, 0, 0.0, 41.0, 41, 41, 41.0, 41.0, 41.0, 41.0, 24.390243902439025, 17.24466463414634, 6.1213795731707314], "isController": false}, {"data": ["GET /api/product/236", 1, 0, 0.0, 35.0, 35, 35, 35.0, 35.0, 35.0, 35.0, 28.57142857142857, 20.200892857142854, 7.170758928571428], "isController": false}, {"data": ["POST /api/auth/login", 30, 0, 0.0, 365.3333333333333, 197, 574, 344.0, 542.2, 566.3, 574.0, 3.104304635761589, 1.7304073106374174, 0.702712709540563], "isController": false}, {"data": ["GET /api/product/275", 1, 0, 0.0, 199.0, 199, 199, 199.0, 199.0, 199.0, 199.0, 5.025125628140704, 3.5480135050251254, 1.261188756281407], "isController": false}, {"data": ["GET /api/product/231", 1, 0, 0.0, 112.0, 112, 112, 112.0, 112.0, 112.0, 112.0, 8.928571428571429, 6.312779017857142, 2.240862165178571], "isController": false}, {"data": ["POST /api/product", 10, 0, 0.0, 232.0, 23, 616, 103.0, 615.3, 616.0, 616.0, 1.5353907569476433, 0.4468227007523415, 0.7102681655918931], "isController": false}, {"data": ["POST /api/orders/221/update (paid)", 1, 0, 0.0, 27.0, 27, 27, 27.0, 27.0, 27.0, 27.0, 37.03703703703704, 11.71875, 12.044270833333334], "isController": false}, {"data": ["GET /api/admin/users", 1, 0, 0.0, 401.0, 401, 401, 401.0, 401.0, 401.0, 401.0, 2.493765586034913, 150.4076722256858, 0.7914783354114713], "isController": false}, {"data": ["GET /api/product/307", 1, 0, 0.0, 25.0, 25, 25, 25.0, 25.0, 25.0, 25.0, 40.0, 27.3828125, 10.0390625], "isController": false}, {"data": ["GET /api/product/308", 1, 0, 0.0, 24.0, 24, 24, 24.0, 24.0, 24.0, 24.0, 41.666666666666664, 28.523763020833332, 10.457356770833334], "isController": false}, {"data": ["GET /api/product/309", 1, 0, 0.0, 38.0, 38, 38, 38.0, 38.0, 38.0, 38.0, 26.31578947368421, 18.040707236842106, 6.604646381578948], "isController": false}, {"data": ["GET /api/product/303", 2, 0, 0.0, 176.5, 27, 326, 176.5, 326.0, 326.0, 326.0, 0.8067769261799113, 0.5503258622428399, 0.20248209963695038], "isController": false}, {"data": ["GET /api/product/304", 1, 0, 0.0, 35.0, 35, 35, 35.0, 35.0, 35.0, 35.0, 28.57142857142857, 19.559151785714285, 7.170758928571428], "isController": false}, {"data": ["POST /api/orders/219/update (completed)", 1, 0, 0.0, 30.0, 30, 30, 30.0, 30.0, 30.0, 30.0, 33.333333333333336, 9.309895833333334, 11.002604166666668], "isController": false}, {"data": ["GET /api/product/305", 1, 0, 0.0, 31.0, 31, 31, 31.0, 31.0, 31.0, 31.0, 32.25806451612903, 22.05141129032258, 8.09601814516129], "isController": false}, {"data": ["GET /api/product/306", 1, 0, 0.0, 45.0, 45, 45, 45.0, 45.0, 45.0, 45.0, 22.22222222222222, 15.190972222222223, 5.577256944444445], "isController": false}, {"data": ["GET /api/product/300", 1, 0, 0.0, 57.0, 57, 57, 57.0, 57.0, 57.0, 57.0, 17.543859649122805, 11.992872807017543, 4.403097587719298], "isController": false}, {"data": ["GET /api/product/223", 2, 0, 0.0, 78.5, 34, 123, 78.5, 123.0, 123.0, 123.0, 0.42643923240938164, 0.30108941897654584, 0.1070262526652452], "isController": false}, {"data": ["GET /api/product/267", 2, 0, 0.0, 28.5, 23, 34, 28.5, 34.0, 34.0, 34.0, 0.5103342689461597, 0.3608222760908395, 0.12808194054605768], "isController": false}, {"data": ["GET /api/product/301", 1, 0, 0.0, 51.0, 51, 51, 51.0, 51.0, 51.0, 51.0, 19.607843137254903, 13.42294730392157, 4.921109068627452], "isController": false}, {"data": ["POST /api/orders/221/update (completed)", 1, 0, 0.0, 25.0, 25, 25, 25.0, 25.0, 25.0, 25.0, 40.0, 11.171875, 13.203125], "isController": false}, {"data": ["GET /api/product/302", 1, 0, 0.0, 106.0, 106, 106, 106.0, 106.0, 106.0, 106.0, 9.433962264150942, 6.458210495283019, 2.367703419811321], "isController": false}, {"data": ["POST /api/orders/223/update (completed)", 1, 0, 0.0, 48.0, 48, 48, 48.0, 48.0, 48.0, 48.0, 20.833333333333332, 5.818684895833333, 6.876627604166667], "isController": false}, {"data": ["POST /api/orders/216/update (paid)", 1, 0, 0.0, 93.0, 93, 93, 93.0, 93.0, 93.0, 93.0, 10.752688172043012, 3.402217741935484, 3.4967237903225805], "isController": false}, {"data": ["POST /api/orders/224/update (paid)", 1, 0, 0.0, 54.0, 54, 54, 54.0, 54.0, 54.0, 54.0, 18.51851851851852, 5.859375, 6.022135416666667], "isController": false}, {"data": ["POST /api/generate-all-copies", 5, 0, 0.0, 2599.0, 2242, 2846, 2629.0, 2846.0, 2846.0, 2846.0, 1.3502565487442615, 0.5735953112341345, 0.505027595868215], "isController": false}, {"data": ["POST /api/orders/215/update (completed)", 1, 0, 0.0, 33.0, 33, 33, 33.0, 33.0, 33.0, 33.0, 30.303030303030305, 8.463541666666666, 10.002367424242424], "isController": false}, {"data": ["POST /api/orders/217/update (completed)", 1, 0, 0.0, 26.0, 26, 26, 26.0, 26.0, 26.0, 26.0, 38.46153846153847, 10.7421875, 12.6953125], "isController": false}, {"data": ["GET /", 1, 0, 0.0, 241.0, 241, 241, 241.0, 241.0, 241.0, 241.0, 4.149377593360996, 355.55384465767634, 0.4700466804979253], "isController": false}, {"data": ["POST /api/orders", 10, 0, 0.0, 51.9, 26, 91, 46.5, 89.60000000000001, 91.0, 91.0, 1.8480872297172426, 0.5342127148401405, 0.5829415773424506], "isController": false}, {"data": ["POST /api/orders/220/update (paid)", 1, 0, 0.0, 28.0, 28, 28, 28.0, 28.0, 28.0, 28.0, 35.714285714285715, 11.300223214285714, 11.614118303571429], "isController": false}, {"data": ["POST /api/generate-copy", 5, 0, 0.0, 2972.8, 2786, 3149, 2977.0, 3149.0, 3149.0, 3149.0, 1.1773016246762422, 0.5001232487638333, 0.4506857781963739], "isController": false}, {"data": ["POST /api/analyze-image", 5, 0, 0.0, 3387.4, 2956, 3656, 3514.0, 3656.0, 3656.0, 3656.0, 1.083658430862592, 0.4603431810793238, 0.3756823661681838], "isController": false}, {"data": ["PUT /api/my-products/edit/300", 1, 0, 0.0, 363.0, 363, 363, 363.0, 363.0, 363.0, 363.0, 2.7548209366391188, 0.7478908402203857, 0.9631112258953168], "isController": false}, {"data": ["GET /api/product/218", 1, 0, 0.0, 33.0, 33, 33, 33.0, 33.0, 33.0, 33.0, 30.303030303030305, 21.425189393939394, 7.605350378787878], "isController": false}, {"data": ["PUT /api/my-products/edit/303", 1, 0, 0.0, 159.0, 159, 159, 159.0, 159.0, 159.0, 159.0, 6.289308176100629, 1.7074488993710693, 2.1926591981132075], "isController": false}, {"data": ["GET /api/product/256", 1, 0, 0.0, 372.0, 372, 372, 372.0, 372.0, 372.0, 372.0, 2.688172043010753, 1.9006216397849462, 0.6746681787634409], "isController": false}, {"data": ["PUT /api/my-products/edit/304", 1, 0, 0.0, 82.0, 82, 82, 82.0, 82.0, 82.0, 82.0, 12.195121951219512, 3.3107850609756095, 4.251619664634146], "isController": false}, {"data": ["PUT /api/my-products/edit/301", 1, 0, 0.0, 346.0, 346, 346, 346.0, 346.0, 346.0, 346.0, 2.890173410404624, 0.784636921965318, 1.0104317196531793], "isController": false}, {"data": ["PUT /api/my-products/edit/302", 1, 0, 0.0, 295.0, 295, 295, 295.0, 295.0, 295.0, 295.0, 3.389830508474576, 0.9202860169491526, 1.1818061440677967], "isController": false}, {"data": ["GET /api/orders", 10, 0, 0.0, 40.0, 23, 63, 38.5, 62.7, 63.0, 63.0, 1.8677624206200971, 1.6206122175009339, 0.45964465819947703], "isController": false}, {"data": ["POST /api/orders/217/update (paid)", 1, 0, 0.0, 90.0, 90, 90, 90.0, 90.0, 90.0, 90.0, 11.11111111111111, 3.515625, 3.61328125], "isController": false}, {"data": ["POST /api/orders/223/update (paid)", 1, 0, 0.0, 54.0, 54, 54, 54.0, 54.0, 54.0, 54.0, 18.51851851851852, 5.859375, 6.022135416666667], "isController": false}, {"data": ["POST /api/orders/218/update (paid)", 1, 0, 0.0, 48.0, 48, 48, 48.0, 48.0, 48.0, 48.0, 20.833333333333332, 6.591796875, 6.77490234375], "isController": false}, {"data": ["GET /api/product/293", 1, 0, 0.0, 31.0, 31, 31, 31.0, 31.0, 31.0, 31.0, 32.25806451612903, 22.082913306451612, 8.09601814516129], "isController": false}, {"data": ["POST /api/detect-product", 5, 0, 0.0, 2351.8, 2030, 2456, 2438.0, 2456.0, 2456.0, 2456.0, 1.6666666666666667, 0.7080078125, 0.5843098958333334], "isController": false}, {"data": ["GET /api/search", 20, 0, 0.0, 174.84999999999997, 51, 456, 71.0, 401.5, 453.29999999999995, 456.0, 3.0988534242330337, 1.0773357607685157, 0.8049755965292842], "isController": false}, {"data": ["PUT /api/my-products/edit/307", 1, 0, 0.0, 24.0, 24, 24, 24.0, 24.0, 24.0, 24.0, 41.666666666666664, 11.311848958333334, 14.567057291666666], "isController": false}, {"data": ["PUT /api/my-products/edit/308", 1, 0, 0.0, 35.0, 35, 35, 35.0, 35.0, 35.0, 35.0, 28.57142857142857, 7.756696428571428, 9.988839285714285], "isController": false}, {"data": ["PUT /api/my-products/edit/305", 1, 0, 0.0, 22.0, 22, 22, 22.0, 22.0, 22.0, 22.0, 45.45454545454545, 12.340198863636365, 15.891335227272728], "isController": false}, {"data": ["PUT /api/my-products/edit/306", 1, 0, 0.0, 23.0, 23, 23, 23.0, 23.0, 23.0, 23.0, 43.47826086956522, 11.80366847826087, 15.200407608695652], "isController": false}, {"data": ["PUT /api/my-products/edit/309", 1, 0, 0.0, 38.0, 38, 38, 38.0, 38.0, 38.0, 38.0, 26.31578947368421, 7.144325657894737, 9.22594572368421], "isController": false}]}, function(index, item){
        switch(index){
            // Errors pct
            case 3:
                item = item.toFixed(2) + '%';
                break;
            // Mean
            case 4:
            // Mean
            case 7:
            // Median
            case 8:
            // Percentile 1
            case 9:
            // Percentile 2
            case 10:
            // Percentile 3
            case 11:
            // Throughput
            case 12:
            // Kbytes/s
            case 13:
            // Sent Kbytes/s
                item = item.toFixed(2);
                break;
        }
        return item;
    }, [[0, 0]], 0, summaryTableHeader);

    // Create error table
    createTable($("#errorsTable"), {"supportsControllersDiscrimination": false, "titles": ["Type of error", "Number of errors", "% in errors", "% in all samples"], "items": []}, function(index, item){
        switch(index){
            case 2:
            case 3:
                item = item.toFixed(2) + '%';
                break;
        }
        return item;
    }, [[1, 1]]);

        // Create top5 errors by sampler
    createTable($("#top5ErrorsBySamplerTable"), {"supportsControllersDiscrimination": false, "overall": {"data": ["Total", 226, 0, "", "", "", "", "", "", "", "", "", ""], "isController": false}, "titles": ["Sample", "#Samples", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors"], "items": [{"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}]}, function(index, item){
        return item;
    }, [[0, 0]], 0);

});
