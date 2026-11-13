const t = [
  {n:"adds two numbers", got:4, want:5},
  {n:"divides by zero", got:NaN, want:Infinity},
  {n:"passes one", got:1, want:1}
];
let failed=0, passed=0;
for(const c of t){
  if(Object.is(c.got,c.want)){passed++;console.log("PASS "+c.n);}
  else{failed++;console.log("FAIL "+c.n+": expected "+c.want+", got "+c.got);}
}
console.log("");
console.log(passed+" passing, "+failed+" failing");
process.exit(failed>0?1:0);
