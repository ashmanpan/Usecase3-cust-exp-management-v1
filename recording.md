# CNC Supports Meeting Recording

**Date:** 2026-03-05
**Source:** CNC Supports-20260305 1517-1.vtt
**Participants:** Krishnaji Panse, Krishnan Thirukonda

---

## Transcript


**Krishnaji Panse:** So Krishna, I will just to give a background that we are actually building one agent TKI use case, and when I discuss this use case with Rana, Rana told me that why you are building, this is already happening into the CNC and PCCA. I will explain the use case to you which I actually written in a mail and then I will understand what portion is already happening and what portion is missing or everything is happening automatically. Yeah. So, so our idea was that the customer explained to us is, they get a lot of call from enterprise, customers that some link gets degraded or something. Happen on a link, right? And link is not down, right? So I, you know, I know if link goes down, then IGP will do the job and then automatically traffic will get routed and all that is right. So that is given, right? So NO problem in that side. But in this case the link is not down. Fundamentally what happens is in. Most of the cases is the underlying optical path gets rerouted. And because of that either a latency get increases and because of some other reasons packet drop get increased or congestion happens on a link and not only one link on a multiple path, right? So what customer was requested to was you identify that particular link using PCA and. And reroute my traffic through some alternative path where the SLA which we are talking to customer that your branch to head office or any branch to branch will actually, get reached within a 60 millisecond or 30 millisecond, right? They actually define that kind of SLAs with customer, that will still become a satisfied, right? So that's the are are we on a same page on a use case specific.

**Krishnan Thirukonda:** Yes, but I have one.

**Krishnaji Panse:** Question here. Yeah.

**Krishnan Thirukonda:** Yeah, so so I think yeah so this is download where packet loss are happening and not readout like you know it was going down. But there are two areas where this can happen, right? One is the PEC links and stuff like that, and then within the network code itself. So if it's PEC links, I think we may not even have alternate path.

**Krishnaji Panse:** Yeah it's yeah.

**Krishnan Thirukonda:** But it's actually great to be easy to use things like PCA. We exactly will be able to say that the PC link is dropping. I mean if they have a lot of access network or that kind of.

**Krishnaji Panse:** Thing right correct so PC link happens that then there is a question about even the PC link is if getting routed on optical one, then there is a question about how we can change optical path and all. If PC links actually facing the same problem, then there is a dual. A link possible, right? One C can talk into two Ps and then we actually do the yeah so those are possibilities but but right now our discussion is not about PC. It is on core because T will run on a core SR will run on a core MPLS T at the core side, right? So it is after the PE discussion.

**Krishnan Thirukonda:** Right, ok, ok. So it's the.

**Krishnaji Panse:** Yeah. PC one also is considered in this use case, but in that case what we will do is not a, not a T tunnel, we will play with IGP and reroute the traffic and do a home perspective if that is possible or we will escalate to the optical guys and they need to do the necessary thing.

**Krishnan Thirukonda:** Right? Right. The only thing I was going to say, the reason I differentiated it is that with PCA or even using IPSLA or, you know, IP endpoint monitoring with SRPM, it's literally easy to find this, assuming that the C is aT1 reflector, right? You can just I mean the basic requirement is you have alternate paths and then you can do something. Well home, you can increase the cost of the dropping paths, all traffic will prefer the other one but if that path goes down, you still need the dropping path at least to send some traffic. So those things are a little bit easy. When you get to port because there are so many links and so many traffic and rerouting is constantly happening, it could be, you know, when you get the PCA end to end PCA session packet loss, it's very hard to pinpoint but we can talk that around.

**Krishnaji Panse:** A bit more yes yeah and and so so you are exactly right. So we are thinking that way only right because we have already a database which will say that ok which L three VPN traffic is running on which link. As soon as PCA pinpoint that ok so and so link has actually degraded. Then we will come to know because of the degradation of that particular link, which of L three VPN or L two VPN is impacted. Out of that, there maybe some selected gold platinum customers, only the, you can say area of worry here or where we need to do the.

**Krishnan Thirukonda:** Okay, so some premium customer traffic the only they are.

**Krishnaji Panse:** Exactly yeah if you are familiar with India, mostly those are HDFC, SBI, ICICI and all those. Those are very, you can say those are armed testing customer. They have a thousand sub branches and if you face a problem on certain branch, they will do a lot of shouting, right? They will come back service providers and all that troubling customers.

**Krishnan Thirukonda:** Yeah sure but one question, you mentioned PCA. Are you planning to put PCA in the network on every link by link? Basically every router will need to have a PCA optic, right? I mean or some other way of sending PCA probes?

**Krishnaji Panse:** Right yes yes, that the customer purchased 50000 sessions. We have around a 2000 Ps in the entire network. So in a, in a start week we will actually start with that and already there are sessions but right now those are a hub to spoke like, but we are actually going ahead and deploying this PCA from every P to every P yes.

**Krishnan Thirukonda:** No, but I'm saying you also need it in the between P to P and between all the P's.

**Krishnaji Panse:** I agree, I agree. So we will do that one also, right? Yes.

**Krishnan Thirukonda:** And then 2nd issue there is that you're using optics, I assume the physical probe, right? From PCA. They only support up to ten gig, right? They don't have higher. I I assume that the core network will have like you know 40 giga hundred gig.

**Krishnaji Panse:** Yeah yeah so so I think I'm not hundred percent sure, but I think the discussion is not optic. They are trying to do some, some software components they are installing on those routers and that mechanism, so NO, it's it's not optic mechanism, yeah.

**Krishnan Thirukonda:** I see, I see. I mean there are other challenges with that one too. Just I mean I'm not a PCA expert, right? But we did a lot of POC even before we acquired accession. So we tried to share containers inside of the CNC app sorry XR app.

**Krishnaji Panse:** Correct correct correct exactly. Yes. Yeah.

**Krishnan Thirukonda:** Yeah, I mean it it'll work but it won't scale like you know for if you have like hundred VRF maybe if you only have like well this is so maybe for core links it's not a big issue. If you learn to run it. No but but but I.

**Krishnaji Panse:** You exactly said it will start from PE, so there is a VRF there, right? And so but but I I agree the only VRF those are platinum one, only those will actually get covered this, right? So basically they are trying to charge something extra to the customer by offering this particular service, right?

**Krishnan Thirukonda:** Okay but I think if it is P to P and P to P the.

**Krishnaji Panse:** Network it might be just simpler.

**Krishnan Thirukonda:** To use SRPM, link SRPM, and then use PCA to collect those metrics.

**Krishnaji Panse:** I agree with you and as soon as we have a full SR, we will do that but today there is NO SR. I see. It will happen, it is our problem only and if you look at the portfolio if we do from something good on a CNC side, some some XR side, some problem is coming. So they need to do some work there. So both guys actually do appropriate work, then only we will be able to roll out yes. So right now there is some and I can give a specific to you, but I'm not.

**Krishnan Thirukonda:** Going detail.

**Krishnaji Panse:** Feature problem which will come some 2622 we discussed with Kamal and they will give us some September October time, then rollout will take another three, six months, right? Then only we will be able to do this. Just for me to connect the dots.

**Krishnan Thirukonda:** Is this like vodafone.

**Krishnaji Panse:** This is world large.

**Krishnan Thirukonda:** Oh geo geo itself. I thought geo, ok, ok. All.

**Krishnaji Panse:** And then same thing we are doing with also.

**Krishnan Thirukonda:** Okay. I handle a.

**Krishnaji Panse:** The 20 accounts in Asia pack. I'm right so so all these you can say population scale accounts are my worry or headache, whatever you.

**Krishnan Thirukonda:** See that way. Sure sure. Okay ok ok yeah ok let's come to yeah I got a picture. Yeah, so so.

**Krishnaji Panse:** So so my our understanding is PCA will detect that particular link, that information will get passed onto CNC or CNC PC integration will give us that which vrfs are affected and as soon as we receive that update, now we are trying to receive that update on, as I asked in my mail on some way of on Kafka and you said ok that's possible and even we can subscribe to that. That update we will take into the AI agent and then AI agent will look at it, ok, what is that link? Then based on the traffic utilization which captured previously and whenever we will have a SR then from SR perspective we will have a more better SRTM traffic matrix also, so we will take that, but today we don't have so we will just look at that, ok, how much is the CEP link is pushing and basis on that, and then. Now we will actually put a tunnel on a alternative path and that that that tunnel should actually take take that VRF, maybe four VRF, three vrf, one VRF that will take the traffic and then SLA will get protected. That is the idea. So, so understanding perspective, I think we are on same page still we will get all. Alert from CNC on a Kafka or getting subscribed on somewhere. Can you give us the details of that how we can actually get that alert?

**Krishnan Thirukonda:** So, I I don't know if you missed it, but the Kafka notification from service health is actually a roadmap. We don't have it today, but we do have notification, we have well we will have GRPC notification in eight.O, which is the next release, but Kafka is further out like maybe end of year eight.one December release. So whatever we.

**Krishnaji Panse:** How we can get this, NO problem what what we, right? We will do the necessary work, but what is the way to get this? Yeah.

**Krishnan Thirukonda:** Yeah so I think we should, let me see if I can just take you to the developer.cisco.com. I don't know if you looked at it already, the note.

**Krishnaji Panse:** The way we tried but the team here on the call was not able to pinpoint, right? Even in API also there are a lot of API but they tried some.

**Krishnan Thirukonda:** Okay let me share here the screen give me a second. Okay so so far I mean seven.two was the latest release, but the API.

**Krishnaji Panse:** We are using we are using.

**Krishnan Thirukonda:** Yeah yeah what I was gonna say is the seven.two documentation for API is still not.

**Krishnaji Panse:** Yeah. Yeah.

**Krishnan Thirukonda:** So I'll show you one, that is all you can find right now on internet or Cisco.com and then if you go to API reference and then go to service and API. So here you will see, you know, how to get notifications, you have to subscribe to notification event stream, you can get a list of all the events.

**Krishnaji Panse:** Streams ok.

**Krishnan Thirukonda:** I think I may even have, either a slideshow or something that I prepared for some meeting. I I can look it up and send it. I don't think we put it in TDM because there's too much detail and it is replicating what is here, but if that helps.

**Krishnaji Panse:** I can send that also. Yeah, share whatever you have and we will try that.

**Krishnan Thirukonda:** Check that we get but basically it's all this, I mean you know JWT and then you go and get a list of monitoring and then you basically your side or the CX development code has to connect and keep the session up and then you will get notification like this and that will which service like you know what is the type service ID. Includes a young path and then the name, you see the name here and then you'll get the what we call as the symptom list, right? So in this whatever you will see you will get basically can be quite detailed, right? Because we I mean if you have a big large service with a lot of rules, you will basically get all the.

**Krishnaji Panse:** You know.

**Krishnan Thirukonda:** Some services and what is wrong and the symptom which is a textual.

**Krishnaji Panse:** You know. Like your BGP I got it. I got it. So this is very good, right? So we will take this right. Now, now in the case.

**Krishnan Thirukonda:** Of let's say you're running overlay using PC.

**Krishnaji Panse:** Yeah.

**Krishnan Thirukonda:** We'll get probe from, like let's say, you know, P in Mumbai to P in Chennai or something like that, right? You will get Usually we don't tell you where the destination is. We will because of the way the whole model is built, we know there are like, you know, hundred sessions or ten sessions going from a PE, and then we'll say which of these sessions are in packet loss or there is some threshold you can set also. So we can say.

**Krishnaji Panse:** E.g. 10 % degradation or 20 % degradation, something like that.

**Krishnan Thirukonda:** Yes, correct. So it'll say that packet loss is about degraded and so on or delays below something. I mean those are the three things we get, which is packet loss delay and delay variation, you can have all three and you get two types. One is forward like source to test and source. So it's a bi directional. So typically on the CNC L three VPN model, we have added we have augmented right the PC integration, so when you create aL3 VPN, you can go and add the probe data like you know what kind of full mesh you want hub and spoke. Again, if you do it is a big issue because the number of sessions.

**Krishnaji Panse:** Can, you know.

**Krishnan Thirukonda:** Multiplier, right? So it can grow large, so we think most people will use hub and spot or you can do custom, like only in certain parts. Most of the net.

**Krishnaji Panse:** You are saying right basically they will have at least two data center or three data center and then every branch will connect to those three data center, right? That is what the normal topology everywhere, yeah, yeah.

**Krishnan Thirukonda:** So all of that is is available. So you should be able to, you know, have PCA session that is controlled by CNC, meaning CNC. So the PCA infrastructure has to be put in place like day zero work is not done by CNC, there's NO automation there, right? It's all either customer or CX has to set it up, register all of those to the PCA controller. And then there is some metadata that you have to exchange like you know on the PCA side for every agent you have to say which is the P you're sitting on, and then we we have a concept of p/interface/VLAN, right? So, if, if an agent is running on a pE/if a PC agent is running on that, when your CNC API is made to create a session. The PCA side gateway will map it to the actual agent and they will configure the web session and send the telemetry of the session back to CNC, and then CNC will come back again the threshold and then send the notification. So that is the let's say the whole you know.

**Krishnaji Panse:** And then by this way we are getting because the session is between C to P, then we will get the exact C sorry sorry P to P, we will get the exact link. If it is a overlay session, then we will not get the exact link. We will say ok something is missing between this P and that PEA and PEB, and then we need to find out another you can.

**Krishnan Thirukonda:** Say, start.

**Krishnaji Panse:** Sessions, not overlay session and then we need to find it out which link is creating this problem, right?

**Krishnan Thirukonda:** Right? Yes, actually that is something we need to talk about, right? What today CNCPC integration does is only overlay between PE and meaning if you want Pepsi or folks to have overlay monitoring monitoring sessions will start from like each PE in the work, but it will go to the other It doesn't go towards C I mean that is customization work that will be.

**Krishnaji Panse:** Needed. Right.

**Krishnan Thirukonda:** See, but we support out of the box the L three VPN model L3P to P only. But the problem with that is there is overlay, meaning we won't know exactly where the packet loss is happening in the So for that, I mean there'll be additional work needed where if the VPN is using a particular SRP binding, then you can find the hub by hop path using topology API, then you can get the packet loss details for each hop either because you're using link SRPM or because you have also.

**Krishnaji Panse:** So if I don't have a SRPM, then I need to use normal PCA sessions which is going from P to P, another P to P and then probably another P to P, right? So though that part I need to figure out from topology and then check it out the data for each of that segment and basis on that figure out where exactly the problem is. Is that understanding right.

**Krishnan Thirukonda:** Yeah, correct. And there is APIs for that. I think we can also stream out, we call it DPM device performance monitoring, right? Basically, all the interface counters are constantly connected and you can that can be streamed out on Kafka by the way, we support Kafka for that and then that's where you can use AI e.g. Example right, you can you know you can have the topology API into your AI and all the data. I mean, it won't be like you know potentially up to 15 min delay here, right? I mean, this is not going to be instantaneous millisecond kind of a response here. So if there is a packet loss happening constantly, it may take ten to 15 min. For all the data for you to get it and then to conclude some link is dropping and then you go and remediate. So for remediation, the option is like either you create well if you want to do it only for a specific VPN, then you have to have every VPN having its own SR policy, and then you can add affinity exclude affinity, right? Exclude that link kind of a thing you can do.

**Krishnaji Panse:** Right, or or we can do the coloring of that particular traffic and basis and traffic, right?

**Krishnan Thirukonda:** Right the rerouting, that's what I'm saying, if you have the VPN, like say Pepsi is a premium but let's say ODN template with the coloring of Pepsi.

**Krishnaji Panse:** Doubts, right?

**Krishnan Thirukonda:** That you can say exclude a lossy link or something like that and then in the when you in this workflow when you detect there is a core link P to P or PE to P link that is dropping, you can go and add through the config either it's in workflow or just NSO. That link you can say is a lossy link, right? Then yes.

**Krishnaji Panse:** RPC also has that, that capability, right? I can say build a tunnel, but don't include that particular link or that particular node, right? That is also there, right?

**Krishnan Thirukonda:** Yeah, so the constraint PC will do calculation, right? So that is yeah PC path calculation, you can say give some constraints, meaning include these type.

**Krishnaji Panse:** Of link that type of link and.

**Krishnan Thirukonda:** But if you do explicit path where you say, you know, go hop by hop and then exclude this link, you can do that also, but I think it may become hard to manage because by using affinity which is you can just say these links have a property called lossy link then automatically all the policies that have like you know you may have multiple VPNs, right? All of them will start avoiding PC you will do the calculation automatically to avoid as soon as you put the property of link on a particular.

**Krishnaji Panse:** Link yeah and that's a.

**Krishnan Thirukonda:** Very simple config, meaning go to the router, go to the router ISIS interface and then say, affinity link and then all the policies immediately will avoid it. We need to recalculate the path. So that maybe a graceful way to do it. The only problem is that, let's say if that. That is the only way to go like if you have like the access ring and all that, right? Some places there is not a lot of options, you know, you have to be careful that you always have a second option when you have that lossy link affinity based because it's a hard thing, right? All the traffic will start avoiding.

**Krishnaji Panse:** Correct, correct. So, so, so, so we cannot ship the entire traffic, right? Because suppose that is a 400 gig link, I cannot ship the entire traffic, I just need to take it out that particular VRF that maybe a one GB or 500 MB or something like that that take it out.

**Krishnan Thirukonda:** Yeah, for that what yeah that's what I said for that what we can do is for every VPN, like Pepsi will have a Pepsi color and Pepsi ODN template, right, for that color and Coke will have its own so that this will be applied only for the Pepsi ODN template to avoid lossy link but Coke will not, right? So that kind of, but basically what it means is every VPN will have to have its own underlay SRD policy and then you will be choosing which policies are, you know, based on the coloring, where you will add this, avoid this link thing. You'll have choice. If you have ten things you'll add where you want to avoid but not the other 90 like we have hundred VPNs, then you have to go and update all these ten things to avoid it.

**Krishnaji Panse:** There is nothing in SRPC which will automatically avoid.

**Krishnan Thirukonda:** You'll not use some of these constraint mechanisms. The other thing you can consider is something called flexalgo. So, but flexalgo as well we don't have a way to by the way, is this SRMPLS or SRMPLS today.

**Krishnaji Panse:** I think they are going to MPLS today, but that is also in a certain area. The area which we are talking where we bring PC the enterprise traffic, there is NO SR today. Yeah, that is pure MPLS.

**Krishnan Thirukonda:** So then the so then we cannot even use SR policy, right? I mean there is NO we cannot.

**Krishnaji Panse:** That's why I was talking about the RSVP tunnel which we can build it out and then reroute the traffic.

**Krishnan Thirukonda:** Oh, so you're actually talking about.

**Krishnaji Panse:** I see. Yeah.

**Krishnan Thirukonda:** Yeah. So for then yeah you can use the exclude.

**Krishnaji Panse:** You know what do you call those? Correct, correct, correct.

**Krishnan Thirukonda:** Right yeah excludes.

**Krishnaji Panse:** Yeah, this one.

**Krishnan Thirukonda:** But also has the affinity concept the.

**Krishnaji Panse:** Yes yeah.

**Krishnan Thirukonda:** So you can have one bit reserved for long. And then the 3rd one I was going to suggest but it won't be granular, meaning it won't affect only some VPN, but it will affect all the VPN which is. We can, we can actually use we have topology APIs where we can also show you the IGP path between two PEs. Let's say yeah wherever you know from PA to peb, there is some loss reported by the overlay session, then you can use the topology API to find all the hops and then hops you can increase, let's say the isis or SPF.

**Krishnaji Panse:** All traffic, I don't think NO NO, the entire traffic will go that that is not the very big links number there are 400 gig links and all, right? That is problem. Yeah.

**Krishnan Thirukonda:** Okay then in that case yeah you can use this topology API to find the the play the all the links, all the pops in the path and then find the and then in RCBT policy configuration you can yeah exclude that hop. Yes.

**Krishnaji Panse:** Okay got it. So, so Krishna, the, my understanding was only the portion till we are sending that alert of this link is degraded till that point you. It was automatic and the remaining portion somebody need to do outside of a CNC. That was my understanding and that's how we are actually building agents which will receive that and as you exactly says then it will actually find it out the topology, then it will go up by hope find out which link and then this is on that link it will actually create our which will avoid that link from the. That was my idea. And that is why I explained to Rana. And Rana said why you are doing this? This is all happening automatically. Is there anything I'm missing?

**Krishnan Thirukonda:** I don't know if she knows that this is not a SR network, right? If this is SR network with affinity we could do it, right? And.

**Krishnaji Panse:** No, but still still that will not happen automatically, right? Somebody need to do that calculation that which exact link is under problem and which we are to that and all.

**Krishnan Thirukonda:** I think there are like, you know, if you don't use AI, you can still use workflow manager. I think you're good.

**Krishnaji Panse:** That that yes yes, so so basically we will use workflow manager plus AI and right finally because selling what AI is easy and valuable than workflow manager, nothing can.

**Krishnan Thirukonda:** Right, right, right, right. Yeah. Okay. Okay. Yeah, I mean the, the, there are some things they are developing which I don't think will be available. I don't know Irona maybe the better person to answer that, whether we will have this AI assistant.

**Krishnaji Panse:** That I know but but that is a future looking one and and I know they are developing, but that is not even an eight.zero committed anything in that, right? So meanwhile we are actually doing this to do the pocs, explain to the customer why you should actually go in a CNC way and how CNC and controller will help them to do actually do this kind of enterprise service management right in in a one way.

**Krishnan Thirukonda:** Yeah, today the best I can say is you can, I mean if you don't want to use AI, what can the platform give you? You can develop workflow automation scripts, you can listen to events, right? You can have the service health. Again, we have a gap where workflow manager does not have subscription capability today. So you'll have to go out, you'll have to have some CX entity that listens to and then calls the workflow to, you know, and then the workflow will have to call like some, let's say Python script or something.

**Krishnaji Panse:** Yeah yeah there is NO.

**Krishnan Thirukonda:** So, like easy way to say, you know, find the link where.

**Krishnaji Panse:** No, NO, that's that's fine that we lot of other use cases we are finding out, you are using your topology APIs and finding our path, we build a knowledge graph which is actually keeps the entire topology also and as soon as there is a change it actually update also, so we built it out that we built it out actually 350 K devices knowledge graph already.

**Krishnan Thirukonda:** Okay, ok. One thing is the DPM point of view, you will also get a threshold crossing alerts, so if you have some link, you don't have to go and let's say, get all the interface, all the packet loss counters. It'll, you can set thresholds, right? Tcas, you will get the notification. You will still need to find the like P to P hop and figure out all the interfaces, then check if you got any TCA or any interface and then Avoid it, meaning avoid.

**Krishnaji Panse:** That link created to find it out the pinpointing link, we need to do this. Yeah, I got it. So we have I mean, I don't know what?

**Krishnan Thirukonda:** Referring to specifically, but we developed some concept mocked UPS and all that. But I like you said, nothing is committed I don't think even we will get something in December timeframe, like December of this year eight.one. There is a lot of work happening, but most of the work is focusing on the agent take like building new that troubleshooting and deep network troubleshooting.

**Krishnaji Panse:** I I only the. Triggering that problem for you if it is a problem. I we actually built it out already those agents do that troubleshooting and then when Javier and I discussed and I actually shown them a lot of use cases, they said NO Krishna, you are asking too much then then discussion. Happen and says, ok, if you want to do only one, then you do this one troubleshooting one, right? So that's the discussion happens. So he said, ok, we will take a troubleshooting one you the remaining one you whatever you want to do, you do it, right? That's what the.

**Krishnan Thirukonda:** Right. Yeah. Okay ok are you gonna use the framework to do the the AI that you're planning to develop for this or is it running separate? Like, you know, the foresight agent framework is supposed to be used by CX also, right? But the SDK is not.

**Krishnaji Panse:** Not completely ready to the what kind of features we need so we already use SDK, we actually saw that. Everything what we build is going nearer to the SDK. So whenever we will have a final SDK available based on our requirement, we will convert those into the yeah.

**Krishnan Thirukonda:** Okay, ok, sounds good. Sounds good. I mean if if you add me in that.

**Krishnaji Panse:** Right, I can see exactly. No, NO NO, I don't think so she probably she's a high level she said but I just don't want to take the chance and get a confirmation from somebody, so I got it now. So, so any questions?

**SWAROOP CHANDRE:** No.

**Krishnan Thirukonda:** No.

**Krishnaji Panse:** You got the API of SRPC, you were able to build a tunnel, you are facing some problem, what was that? Do you want to discuss that here?

**Utkarsh Singh:** Yeah, so I have a couple of APIs that i'm using to build the tunnel yeah just a second. I'll just.

**Krishnaji Panse:** Yeah you are getting some null error.

**Utkarsh Singh:** Something error, right? Yeah, yeah, yeah, yeah. Yeah, so these are the APIs that basically i'm using, but this one is for RSVP tunnel, and then there is one more this there is one for dry run and then create a SR policy also. So this I'm getting couple of things failure because I think the devices in the lab are not configured for the appropriate.

**Krishnaji Panse:** Policies. So YESR will not work, but RS RS 51 is.

**Utkarsh Singh:** It's also not working giving it's giving null.

**Krishnaji Panse:** As of now. So Krishna, are we using the right API here just to confirm that, then we will verify the device side if you just confirm.

**Krishnan Thirukonda:** Well, there are two APIs. I see you're using the PC initiated API. There is also PCC like we can go configure the head end. I actually recommend that so that easier to troubleshoot. I mean the will be on the, on the, it depends. Do you want this temporary policy or you want to have them all the time? If you want to have them all the time, it's better to put it on the router using.

**Krishnaji Panse:** This is a temporary one, right? As soon as the degradation of link is coming back and link is on, then we will delete this one, right? That is the idea.

**Krishnan Thirukonda:** I see.

**Krishnaji Panse:** Because so many will get created continuously, so every time it should be automated mechanism that every time we see the link is back and stable, right? Up to the non degradation SLA which we think is right, then this will get automatically deleted also.

**Krishnan Thirukonda:** But there is some problem here. So one is how do you steer traffic into this RSBT like you know for specific works? It's not easy in the RSBT, right? It's segment routing is easy because you have something called on demand template and automated.

**Krishnaji Panse:** Steering.

**Krishnan Thirukonda:** Yeah, here if you create between on a PE, a policy, if you do auto announce then all.

**Krishnaji Panse:** All the VPNs will start doing. We cannot do, yeah, yeah. So I discussed with one of the SR experts and he said that we can actually point saying ok, traffic towards the tunnel, and then instead of going through that we will actually send the traffic from a tunnel, right? So that is the idea.

**Krishnan Thirukonda:** Yeah, so for that you'll have to either say next hop instead of giving the loopback zero of the remote P you will give for the one that is pushing through the Yeah that'll be more needed. I think through NSO because of all that. If you do like this, right, what will happen is on the, on the router, there is NO let's say configured state and there's only operational state. There'll be a tunnel appear if you do show tunnels, but if you do show running complete, there is NO.

**Krishnaji Panse:** Yes yes.

**Krishnan Thirukonda:** So I mean you may want to consider that, but yeah, this is called the PCE initiated, meaning through the tunnel. Yes. But steering traffic into this maybe challenging because there is NO, let's say handle on the.

**Krishnaji Panse:** Okay so you you are saying do the PCC be right initiated and so NSO will put the configuration directly on the router, we will be able to see that also and then maintain that for certain duration, and as soon as we see there is NO need of right right let NSO go and reward back that one right we just need to do revert back on NSO side, right?

**Krishnan Thirukonda:** Yeah, anyway, we are working in the order of minutes, right? Nothing is happening in milliseconds, right? So.

**Krishnaji Panse:** No NO NO NO 1 h 2 h that link will not not not will get sorted out, then only we are doing this, right? Right, right. There is NO point in creating a tunnel for 5 min and then deleting it.

**Krishnan Thirukonda:** Right, there is NO point. Agree. Agree. Yeah because with the NSO the only challenge is like if you're doing a lot of provisioning operations, there maybe, you know, if you're using async mode, then it's fine, but if you think mode, you know, you'll probably.

**Krishnaji Panse:** No better than me. Then you need to wait for queue right with a lot of closed loop configurations which we do we actually saw that problem. I agree with you, yeah.

**Krishnan Thirukonda:** So for we have something called LCM local congestion.

**Krishnaji Panse:** Mitigation in with.

**Krishnan Thirukonda:** Using PC initiated to avoid all that stuff, right? So we use this this kind of API but for doing something from outside where it's ok and you have to do some steering like you know traffic steering, you have to go to the work and say now you have to change the next top use the the tunnel endpoint IP address, right? So the traffic for only that work will you know go through that. So that maybe it maybe better to link all of that in a model extension on the recommendation.

**Krishnaji Panse:** So for that there is a different API.

**Krishnan Thirukonda:** The T tunnel API you can.

**Krishnaji Panse:** You can use. The other thing is that the reason.

**Krishnan Thirukonda:** But this may not be working, I saw an error for the SRMPLS where it said HTTP is not configured, maybe your PC was not onboarded with the HTTP endpoint also defined because we need HTTP for this PC in it API work. Okay.

**Krishnaji Panse:** Oh, that is a problem now then some vulnerability is saying you should disable the HTTP and.

**Krishnan Thirukonda:** Okay. Yeah, for RSVT we need HTTP. We are moving to GRPC but Fort the GRPC API or the.

**Krishnaji Panse:** So we do need.

**Krishnan Thirukonda:** For this work as long as the PCE is onboarded ONC with HTTP.

**Krishnaji Panse:** It should work.

**Krishnan Thirukonda:** And let me know. I mean you can sort of email thread with me and Blinfong is in your.

**Krishnaji Panse:** Is my neighbor yes.

**Krishnan Thirukonda:** Oh, yeah, yeah. Oh, you're in singapore.

**Krishnaji Panse:** Yeah, I'm in Singapore, but these are all my team members in Mumbai. Yeah ok so so I will we'll start with you and Lim and then we'll take help from you. We'll try it out, ok? And we will share with you the entire use case documentation what we are trying to do, even if you are interested I don't know, then code also and then you can have a look at it before what we are doing and then suggest whatever if we are missing anything. No exactly because I think.

**Krishnan Thirukonda:** There will be other customers that are interested and I, yeah, I mean CXPM folks are located here, I will give them also a hints that this is available meaning if they, if they are looking forward like I mean this is a common ask by the way, the brown out.

**Krishnaji Panse:** I know I know, I know, yeah, yeah, yeah. By the way Krishna I'm not from CX NO but but we are working with CX and then CX team member. From some of those are here on our CX side, so we are doing combinations, some of the portion of my team members and some we are jointly building this.

**Krishnan Thirukonda:** I see ok ok yeah yeah and this is for geo, right? At least at the moment.

**Krishnaji Panse:** And then you will. And then but we are talking to a lot of customers, I just presented the entire agent UI use cases for optus yesterday, then Globe is asking this. We are actually doing a POC with globe. The Softbank and Rakuten is exactly asking this. I was saying if you show me this use case I will give.

**Krishnan Thirukonda:** Okay ok that's good.

**Krishnaji Panse:** Okay yeah but yeah specifically just for it.

**Krishnan Thirukonda:** Which they are pushing us to help with SRV six. So we are there going to be some early adoption of SRV six with the.

**Krishnaji Panse:** That I know that we are asking the date and then we say condition mitigation and that is global GCM will happen, right?

**Krishnan Thirukonda:** Sure, correct. There are some issues right now on the.

**Krishnaji Panse:** Yeah silicon.

**Krishnan Thirukonda:** Someone itself is not able to do something.

**Krishnaji Panse:** At the moment yeah when we build that network I was at CX side, so my team only instrumented to build that. So if I created a problem, I created a problem for me.

**Krishnan Thirukonda:** Okay ok got it. Yeah. Okay, very good. I can I mean for like let's say if as you implemented if you have issues, yeah, keep me and Lim on my email copy and or maybe create a Webex team room.

**Krishnaji Panse:** Either way whatever I'm in the.

**Krishnan Thirukonda:** Limits of course in.

**Krishnaji Panse:** Singapore and.

**Krishnan Thirukonda:** I'm just trying to think if anybody else NO I think their time we will talk to him.

**Krishnaji Panse:** At the night time whenever you are awake we will talk to you, right? No problem. Okay, ok. Thanks. Thanks. Anybody has any question?

**Bhalchandra Gangshettiwar:** Anybody.

**Krishnaji Panse:** All good. Okay, thanks Christian. Thank you very much. I was actually looking for 5th of February I was talking nobody was ready to reply me, you only the person.
